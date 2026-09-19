"""Render a sampled ground-truth profile into free-text CV prose with Claude.

The renderer only ever sees RAW FACTS: role titles, employers, date strings exactly
as they must appear, per-role skill labels, projects, education, certificates,
languages and eligibility hints. It never sees months totals, seniority, per-skill
durations or anything else derived, and the system prompt forbids stating a
duration. If the CV said "5 years of Python" we would be measuring the extractor's
reading comprehension instead of its date arithmetic.
"""
from __future__ import annotations

import concurrent.futures
import json
import random
import re
import time
from pathlib import Path
from typing import Any

from .. import config
from ..dates import ym_to_index
from ..schemas import Profile
from .sampler import STYLES, _named_in  # noqa: F401  (STYLES re-exported for callers)

_MD_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+", re.M)
_MD_BULLET = re.compile(r"^(\s*)[*+]\s+", re.M)
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*", re.S)
_MD_FENCE = re.compile(r"^\s*```.*$", re.M)
# a duration statement is the one thing the renderer must never produce
DURATION_RE = re.compile(
    r"\b(\d+\s*\+?\s*(?:years?|yrs?\.?|months?|mos\.?)"
    r"|(?:one|two|three|four|five|six|seven|eight|nine|ten|several|many)\s+(?:years?|months?)"
    r"|(?:over\s+)?a\s+decade)\b", re.I)


def strip_markdown(text: str) -> str:
    """CV text extracted from a PDF has no markdown. The model complies with rule 7
    most of the time; this makes it unconditional."""
    text = _MD_FENCE.sub("", text)
    text = _MD_HEADING.sub("", text)
    text = _MD_BOLD.sub(r"\1", text)
    text = _MD_BULLET.sub(r"\1- ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def reconcile_meta(meta: dict, text: str, *, taxonomy) -> dict:
    """`omitted_skills` must mean "absent from the rendered CV", not "intended to be
    absent". Generic aliases leak: a CV that never lists CI/CD can still say
    "deployment pipeline". Any such skill is moved back to the stated set, so the
    stated-vs-omitted recall split measures what it claims to."""
    low = text.lower()
    kept, leaked = [], []
    for sid in meta.get("omitted_skills") or []:
        (leaked if _named_in(sid, low, taxonomy) else kept).append(sid)
    meta["omitted_skills"] = kept
    meta["leaked_skills"] = leaked
    meta["under_report"] = bool(kept)
    meta["duration_phrases"] = sorted({m.group(0) for m in DURATION_RE.finditer(text)})
    return meta

SYSTEM = """You write realistic CV / resume documents in plain text.

You are given a JSON object of RAW FACTS about one fictional candidate and a STYLE
directive. Turn the facts into a believable CV.

HARD RULES (a violation makes the document useless):
1. NEVER state a duration, total or span. No "5 years", "3+ years", "over a decade",
   "five years of Python", "since 2019 (7 years)", "2 yrs". No counts of years or
   months anywhere, in any section, including a summary line. Dates are allowed;
   arithmetic on them is not.
2. Dates must appear EXACTLY as written in the JSON `dates` field of each role, and
   nowhere else invent a date. Do not convert, expand or reformat them.
3. Use a fictional name and fictional contact details (email, phone, city). Do not
   reuse any name from the JSON; the JSON contains no name.
4. Do not add skills, technologies, employers, projects, certificates, degrees or
   languages that are not in the JSON. You may rephrase a skill label naturally
   (e.g. "Kubernetes (k8s)") but must not introduce a new one.
5. Do not state a seniority level, a proficiency rating, a number of projects, or
   any summary statistic.
6. Never mention age, date of birth, gender, nationality, marital status, health, a
   photo, or a graduation year.

7. Output PLAIN TEXT, the way a CV looks after a PDF is converted to text. No
   markdown at all: no "#" headings, no "**bold**", no "*" bullets, no tables, no
   code fences. Plain section headings on their own line and "-" for bullets if the
   style calls for bullets.

Write bullets and sentences that describe what the person did, grounded in the
listed skills for that role. Vary phrasing between roles. No JSON, no preamble, no
commentary. Start with the candidate's name on the first line.

Before you answer, re-read rule 1 and rule 7. The two failures we see most often are
a stray "3 years" in a summary line and markdown formatting characters."""

_LEVEL_LABEL = {
    "none": None,
    "secondary": "Upper secondary school diploma (lukio)",
    "vocational": "Vocational qualification (ammattitutkinto) in Information Technology",
    "bsc": "B.Sc.",
    "msc": "M.Sc.",
    "phd": "Ph.D.",
}
_CERT_LABEL = {
    "aws_saa": "AWS Certified Solutions Architect - Associate",
    "cka": "Certified Kubernetes Administrator (CKA)",
    "ckad": "Certified Kubernetes Application Developer (CKAD)",
    "scrum_master": "Certified ScrumMaster (CSM)",
    "istqb_foundation": "ISTQB Certified Tester, Foundation Level",
    "azure_az900": "Microsoft Certified: Azure Fundamentals (AZ-900)",
}
_CITY = {"FI": ["Helsinki", "Espoo", "Tampere", "Turku", "Oulu", "Vantaa"],
         "EE": ["Tallinn", "Tartu"], "SE": ["Stockholm", "Gothenburg"]}
_MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _fmt_date(ym: str, *, year_only: bool, as_of: str, is_end: bool) -> str:
    if is_end and ym == as_of[:7]:
        return "Present"
    y, m = ym.split("-")
    return y if year_only else f"{_MONTH_NAMES[int(m) - 1]} {y}"


def _fmt_range(start: str, end: str, *, year_only: bool, as_of: str) -> str:
    s = _fmt_date(start, year_only=year_only, as_of=as_of, is_end=False)
    e = _fmt_date(end, year_only=year_only, as_of=as_of, is_end=True)
    return f"{s}-{e}" if year_only and e != "Present" else f"{s} – {e}"


def build_view(truth: Profile, meta: dict, *, taxonomy) -> dict[str, Any]:
    """The JSON the renderer is allowed to see. Raw facts only: no months, no
    totals, no seniority, no proficiency, no derived booleans."""
    omitted = set(meta.get("omitted_skills") or [])
    year_only = bool(meta.get("year_only_dates"))
    as_of = truth.as_of

    roles = []
    for r in sorted(truth.experience.roles, key=lambda x: ym_to_index(x.start), reverse=True):
        labels = [taxonomy.label(s) for s in r.skills_mentioned if s not in omitted]
        highlight = [taxonomy.label(s) for s in r.primary_skills if s not in omitted]
        roles.append({
            "title": r.title_raw,
            "employer": r.employer,
            "dates": _fmt_range(r.start, r.end, year_only=year_only, as_of=as_of),
            "skills_used": labels,
            "emphasise": highlight,
        })

    projects = [{
        "title": p.title,
        "focus": list(p.topics),
        "skills_used": [taxonomy.label(s) for s in p.skills if s not in omitted],
        "deployed": p.deployed,
    } for p in truth.projects]

    level = truth.education.highest_level.value
    education = None
    if _LEVEL_LABEL.get(level):
        education = {
            "qualification": _LEVEL_LABEL[level],
            "subject": truth.education.field.value,
            "in_progress": bool(truth.education.in_progress.value),
            "note": "Do not write a graduation year.",
        }

    country = truth.eligibility.location_country.value or "FI"
    hints = [f"Lives in {random.Random(meta.get('idx', 0)).choice(_CITY.get(country, ['Helsinki']))}, "
             f"{ {'FI': 'Finland', 'EE': 'Estonia', 'SE': 'Sweden'}.get(country, country) }"]
    if truth.eligibility.requires_sponsorship.value is True:
        hints.append("Needs a work permit / visa sponsorship to work in Finland - may mention it plainly")
    if truth.eligibility.relocation_willing.value is True:
        hints.append("Open to relocation")

    block = sorted({s for r in truth.experience.roles for s in r.skills_mentioned}
                   | set(meta.get("block_only_skills") or []))
    return {
        "style": meta.get("style", STYLES[0]),
        "roles_reverse_chronological": roles,
        "projects": projects,
        "education": education,
        "certifications": [_CERT_LABEL.get(c.cert_id, c.cert_id) for c in truth.certifications],
        "languages": [{"language": l.lang, "level": l.cefr} for l in truth.languages],
        "personal_hints": hints,
        "skills_section_labels": [taxonomy.label(s) for s in block if s not in omitted],
    }


# --------------------------------------------------------------------------- #
# Claude call
# --------------------------------------------------------------------------- #

def _client():
    import anthropic
    return anthropic.Anthropic()


def render_cv(truth: Profile, meta: dict, *, taxonomy, client=None, max_retries: int = 4) -> str:
    """Render one CV. Raises RuntimeError if the model refuses."""
    import anthropic

    view = build_view(truth, meta, taxonomy=taxonomy)
    client = client or _client()
    user = (
        "STYLE: " + view["style"] + "\n\n"
        "RAW FACTS (JSON):\n" + json.dumps(view, indent=1, ensure_ascii=False) + "\n\n"
        "Write the CV now. Remember: no durations, no year counts, dates exactly as given, "
        "fictional name and contact details, nothing invented beyond the facts above."
    )
    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = client.messages.create(
                model=config.MODEL_ID,
                max_tokens=4000,
                system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}],
                output_config={"effort": "low"},
            )
        except (anthropic.RateLimitError, anthropic.APIConnectionError) as exc:
            last_err = exc
            time.sleep(2 ** attempt)
            continue
        except anthropic.APIStatusError as exc:
            last_err = exc
            if exc.status_code and 500 <= int(exc.status_code) < 600:
                time.sleep(2 ** attempt)
                continue
            raise
        if getattr(resp, "stop_reason", None) == "refusal":
            raise RuntimeError(f"renderer refused for synth_{meta.get('idx')}")
        text = next((b.text for b in resp.content if getattr(b, "type", None) == "text"), None)
        if not text:
            last_err = RuntimeError("no text block in response")
            continue
        return strip_markdown(text)
    raise RuntimeError(f"render failed after {max_retries} attempts: {last_err!r}")


# --------------------------------------------------------------------------- #
# corpus
# --------------------------------------------------------------------------- #

def render_corpus(n: int, seed: int, out_dir: Path | str = config.SYNTH_DIR,
                  force: bool = False, max_workers: int = 6) -> list[dict]:
    """Sample `n` truths and render each to `{out_dir}/synth_{i:03d}.txt`, writing
    `.truth.json` and `.meta.json` alongside. Existing files are kept unless
    `force`, so re-running the eval costs nothing."""
    from ..loaders import load_manifest, load_taxonomy
    from .sampler import sample_corpus

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    taxonomy = load_taxonomy()
    manifest = load_manifest("software_engineering.json")
    corpus = sample_corpus(n, seed, taxonomy=taxonomy, manifest=manifest)

    # truth is cheap and deterministic: always rewrite it.
    for i, (truth, _meta) in enumerate(corpus):
        (out / f"synth_{i:03d}.truth.json").write_text(truth.model_dump_json(indent=1))

    todo = [i for i in range(n) if force or not (out / f"synth_{i:03d}.txt").exists()]
    errors: list[tuple[int, str]] = []
    if todo:
        client = _client()

        def _one(i: int) -> None:
            truth, meta = corpus[i]
            text = render_cv(truth, meta, taxonomy=taxonomy, client=client)
            (out / f"synth_{i:03d}.txt").write_text(text)

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_one, i): i for i in todo}
            for fut in concurrent.futures.as_completed(futures):
                i = futures[fut]
                try:
                    fut.result()
                except Exception as exc:  # keep going; report at the end
                    errors.append((i, repr(exc)))

    records = []
    for i, (truth, meta) in enumerate(corpus):
        txt = out / f"synth_{i:03d}.txt"
        if txt.exists():
            reconcile_meta(meta, txt.read_text(), taxonomy=taxonomy)
        (out / f"synth_{i:03d}.meta.json").write_text(json.dumps(meta, indent=1))
        records.append({
            "idx": i,
            "text_path": str(out / f"synth_{i:03d}.txt"),
            "truth_path": str(out / f"synth_{i:03d}.truth.json"),
            "meta_path": str(out / f"synth_{i:03d}.meta.json"),
            "rendered": (out / f"synth_{i:03d}.txt").exists(),
            "meta": meta,
        })
    if errors:
        print(f"[render_corpus] {len(errors)} render failures: {errors[:5]}")
    return records
