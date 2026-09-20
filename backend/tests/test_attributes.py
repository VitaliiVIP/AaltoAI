"""The parse-inspection view: what we read, and the words we read it from.

The invariant worth a test is the one the UI cannot check for itself — that
every offset still indexes the text the endpoint ships, and that a protected
attribute cannot appear in a list built by walking a profile.
"""
import pytest
from fastapi.testclient import TestClient

from recourse_screen.api.app import app
from recourse_screen.api.attributes import attributes_for
from recourse_screen.loaders import load_cv_text, load_job, manifest_for_job
from recourse_screen.pipeline import candidate_profile
from recourse_screen.schemas import NEVER_EXTRACT

CANDIDATE = "cv1_elina_korhonen"


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def parse(client):
    res = client.get(f"/candidates/{CANDIDATE}/cv")
    assert res.status_code == 200
    return res.json()


def test_every_offset_indexes_the_text_that_shipped_with_it(parse):
    """The highlight is a slice, not a search: if this drifts the UI marks the
    wrong words, which is worse than showing no highlight at all."""
    text = parse["text"]
    spans = [e for a in parse["attributes"] for e in a["evidence"] if e["start"] is not None]
    assert spans, "the demo CV should have located quotes"
    for ev in spans:
        assert text[ev["start"]:ev["end"]] == ev["quote"]
        assert ev["verified"] is True


def test_unverified_quotes_carry_no_offsets(parse):
    for attr in parse["attributes"]:
        for ev in attr["evidence"]:
            if not ev["verified"]:
                assert ev["start"] is None and ev["end"] is None


def test_absent_attributes_are_listed_rather_than_dropped(parse):
    """"The CV did not say" is the one thing this screen exists to show."""
    absent = [a for a in parse["attributes"] if a["derivation"] == "absent"]
    assert absent and all(a["evidence"] == [] for a in absent)


def test_computed_attributes_are_marked_as_computed(parse):
    total = next(a for a in parse["attributes"] if a["path"] == "experience.total_months")
    assert total["derivation"] == "computed" and total["evidence"] == []


def test_scored_flag_matches_the_job(parse):
    job = load_job("data_scientist")
    decided = set(job.score) | {ko.path for ko in job.parsed_knockouts}
    flagged = {a["path"] for a in parse["attributes"] if a["scored"]}
    # Skills collapse to their `.held` row, so a scored `skills.x.months` is
    # flagged on `skills.x.held`; every other flagged path is decided directly.
    assert flagged <= decided | {p.rsplit(".", 1)[0] + ".held" for p in decided}
    assert "education.highest_level" in flagged


def test_no_protected_attribute_is_ever_listed(parse):
    labels = " ".join(f"{a['path']} {a['label']}" for a in parse["attributes"]).lower()
    for field in NEVER_EXTRACT:
        assert field.replace("_", " ") not in labels
    assert "graduation_year" not in labels and "max_gap_months" not in labels


def test_attributes_do_not_need_a_job_to_be_listed():
    """The projection is a view of the profile; the job only adds the flag."""
    profile = candidate_profile(CANDIDATE)
    rows = attributes_for(profile)
    assert rows and not any(r["scored"] for r in rows)
    assert len(rows) == len(attributes_for(profile, manifest_for_job(load_job("data_scientist"))))


def test_unknown_candidate_is_a_404(client):
    assert client.get("/candidates/no_such_cv/cv").status_code == 404


def test_candidate_id_cannot_escape_the_cv_directory():
    with pytest.raises(KeyError):
        load_cv_text("../../../etc/passwd")
