"""Uploaded CVs are served back by the API; demo CVs are not (they ship with the
frontend). What matters here is that the id off the URL can never reach outside
the uploads directory, and that an upload without a thumbnail gets one on demand."""
import shutil

import pytest
from fastapi.testclient import TestClient

from recourse_screen import config
from recourse_screen.api.app import app

DEMO_PDF = config.BACKEND_DIR.parent / "frontend" / "public" / "assets" / "cvs" / "cv1_elina_korhonen.pdf"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "UPLOADS_DIR", tmp_path)
    return TestClient(app)


@pytest.mark.parametrize("cid", ["nobody", "..", "../cv1_elina_korhonen", ".hidden", "a/b"])
def test_unknown_or_unsafe_ids_are_404(client, cid):
    assert client.get(f"/candidates/{cid}/file.pdf").status_code == 404
    assert client.get(f"/candidates/{cid}/thumbnail.png").status_code == 404


def test_demo_cv_is_not_served_by_the_api(client):
    """The demo pool's files live in the frontend build; `has_pdf` is what tells the UI."""
    assert client.get("/candidates/cv1_elina_korhonen/file.pdf").status_code == 404
    rows = client.get("/candidates").json()
    assert all(r["has_pdf"] is False for r in rows)


@pytest.mark.skipif(not DEMO_PDF.exists() or shutil.which("pdftoppm") is None,
                    reason="needs the demo PDF and poppler")
def test_uploaded_pdf_and_lazy_thumbnail(client, tmp_path):
    shutil.copy(DEMO_PDF, tmp_path / "someone.pdf")

    res = client.get("/candidates/someone/file.pdf")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content[:5] == b"%PDF-"

    assert not (tmp_path / "someone.png").exists()
    res = client.get("/candidates/someone/thumbnail.png")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert res.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert (tmp_path / "someone.png").exists(), "rendered once, then served as a file"
