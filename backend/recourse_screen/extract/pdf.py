"""PDF -> text and content hashing.

`pdftotext -layout` (poppler) is used rather than a Python PDF library because the
layout mode preserves the two-column "Title .... Aug 2025-Present" role headers that
real CVs use, and those headers are what the extractor quotes as evidence.

The sha256 of the *text* (not the PDF bytes) is the cache key, so re-exporting the same
CV from Word does not force a re-extraction.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

__all__ = ["PdfExtractionError", "pdf_to_text", "pdf_to_png", "sha256_text", "load_cv_text"]


class PdfExtractionError(RuntimeError):
    """pdftotext is missing or failed on this file."""


def pdf_to_text(pdf_path: str | Path) -> str:
    """Extract the embedded text layer of a PDF with `pdftotext -layout`.

    Raises PdfExtractionError if poppler is not installed or the file cannot be read.
    Note: this reads the *embedded text layer only*. Per the injection brief, a
    production pipeline would also OCR the rendered page and diff the two renderings
    to catch invisible-text injections; that comparison is out of scope for the demo.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise PdfExtractionError(f"no such PDF: {path}")
    if shutil.which("pdftotext") is None:
        raise PdfExtractionError(
            "pdftotext not found on PATH; install poppler-utils to parse PDFs"
        )
    try:
        proc = subprocess.run(
            ["pdftotext", "-layout", str(path), "-"],
            capture_output=True,
            check=True,
            timeout=60,
        )
    except subprocess.CalledProcessError as exc:  # pragma: no cover - env dependent
        raise PdfExtractionError(
            f"pdftotext failed on {path}: {exc.stderr.decode('utf-8', 'replace')[:400]}"
        ) from exc
    except subprocess.TimeoutExpired as exc:  # pragma: no cover - env dependent
        raise PdfExtractionError(f"pdftotext timed out on {path}") from exc
    return proc.stdout.decode("utf-8", "replace")


def pdf_to_png(pdf_path: str | Path, png_path: str | Path, *, dpi: int = 100) -> Path:
    """Render page 1 of a PDF to a PNG with `pdftoppm` -- the card thumbnail.

    Same settings as `make add-cv` uses for the demo pool, so an upload and a
    demo CV look alike in the list. Raises PdfExtractionError if poppler is
    missing or the render fails; callers treat that as "no thumbnail", not as a
    failed upload.
    """
    src, dst = Path(pdf_path), Path(png_path)
    if not src.exists():
        raise PdfExtractionError(f"no such PDF: {src}")
    if shutil.which("pdftoppm") is None:
        raise PdfExtractionError("pdftoppm not found on PATH; install poppler-utils")
    if dst.suffix.lower() != ".png":
        raise ValueError(f"thumbnail path must end in .png: {dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    # -singlefile writes exactly `<prefix>.png`, no page-number suffix to rename.
    prefix = dst.with_suffix("")
    try:
        subprocess.run(
            ["pdftoppm", "-png", "-r", str(dpi), "-f", "1", "-l", "1", "-singlefile",
             str(src), str(prefix)],
            capture_output=True,
            check=True,
            timeout=60,
        )
    except subprocess.CalledProcessError as exc:  # pragma: no cover - env dependent
        raise PdfExtractionError(
            f"pdftoppm failed on {src}: {exc.stderr.decode('utf-8', 'replace')[:400]}"
        ) from exc
    except subprocess.TimeoutExpired as exc:  # pragma: no cover - env dependent
        raise PdfExtractionError(f"pdftoppm timed out on {src}") from exc
    if not dst.exists():
        raise PdfExtractionError(f"pdftoppm produced no output for {src}")
    return dst


def sha256_text(text: str) -> str:
    """Stable content hash of the CV text; the cache key for raw output and profiles."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_cv_text(path: str | Path) -> str:
    """Read a CV from a .txt or .pdf path and return its plain text."""
    p = Path(path)
    if p.suffix.lower() == ".pdf":
        return pdf_to_text(p)
    return p.read_text(encoding="utf-8")
