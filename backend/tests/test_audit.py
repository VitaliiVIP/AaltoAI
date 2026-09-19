"""Append-only, hash-chained decision log."""
import json
from pathlib import Path

from recourse_screen.audit.log import (
    GENESIS_HASH,
    append_record,
    get_record,
    make_payload,
    read_records,
    verify_chain,
)
from recourse_screen.loaders import load_job, load_manifest, load_profile
from recourse_screen.recourse.ranking_mode import run_ranking_mode
from recourse_screen.recourse.threshold_mode import run_threshold_mode

FIXTURES = Path(__file__).parent / "fixtures"


def toy():
    return (
        load_profile(FIXTURES / "toy_profile.json").model_copy(deep=True),
        load_job(FIXTURES / "toy_job.yaml").model_copy(deep=True),
        load_manifest(FIXTURES / "toy_manifest.json"),
    )


def test_three_records_form_a_valid_chain(tmp_path):
    log = tmp_path / "audit.jsonl"
    records = [append_record({"n": i}, path=log) for i in range(3)]

    assert records[0].prev_hash == GENESIS_HASH
    assert [r.prev_hash for r in records[1:]] == [r.hash for r in records[:-1]]
    assert len({r.decision_id for r in records}) == 3
    assert verify_chain(log) == (True, 3, None)
    assert len(log.read_text().strip().splitlines()) == 3


def test_records_are_readable_back_by_decision_id(tmp_path):
    log = tmp_path / "audit.jsonl"
    append_record({"n": 0}, path=log)
    target = append_record({"n": 1}, decision_id="abc123", path=log)
    append_record({"n": 2}, path=log)

    assert get_record("abc123", path=log) == target
    assert get_record("nope", path=log) is None
    assert [r.payload["n"] for r in read_records(log)] == [0, 1, 2]


def test_tampering_with_a_payload_is_detected_at_that_index(tmp_path):
    log = tmp_path / "audit.jsonl"
    for i in range(3):
        append_record({"n": i, "decision": "reject"}, path=log)

    lines = log.read_text().splitlines()
    doctored = json.loads(lines[1])
    doctored["payload"]["decision"] = "pass"
    lines[1] = json.dumps(doctored)
    log.write_text("\n".join(lines) + "\n")

    ok, count, first_bad = verify_chain(log)
    assert ok is False and count == 3 and first_bad == 1


def test_deleting_a_record_breaks_the_chain(tmp_path):
    log = tmp_path / "audit.jsonl"
    for i in range(3):
        append_record({"n": i}, path=log)
    lines = log.read_text().splitlines()
    log.write_text("\n".join([lines[0], lines[2]]) + "\n")

    ok, count, first_bad = verify_chain(log)
    assert ok is False and count == 2 and first_bad == 1


def test_missing_log_verifies_as_an_empty_chain(tmp_path):
    assert verify_chain(tmp_path / "nothing.jsonl") == (True, 0, None)
    assert read_records(tmp_path / "nothing.jsonl") == []


def test_threshold_mode_payload_is_json_serialisable_and_complete(tmp_path):
    profile, job, manifest = toy()
    outcome = run_threshold_mode(profile, job, manifest)
    payload = make_payload(
        outcome, mode="A", job=job, manifest=manifest, profile=profile,
        candidate_id="c", cv_sha256="deadbeef", explanation_hash=None,
        versions={"extract_prompt_version": "extract-v1"},
    )
    assert payload["mode"] == "A"
    assert payload["tau"] == 60 and payload["score"] == 47
    assert payload["decision"]["passed"] is False
    assert len(payload["actions_shown"]) == 3
    assert payload["protected_exclusion_assert_passed"] is True
    assert payload["immutable_blockers"] == []
    assert payload["raw_cv_hash"] == "deadbeef"
    assert len(payload["profile_hash"]) == 64
    assert payload["versions"]["manifest_version"] == "toy-v1"

    record = append_record(payload, path=tmp_path / "audit.jsonl")
    assert verify_chain(tmp_path / "audit.jsonl") == (True, 1, None)
    assert json.loads(record.model_dump_json())["payload"]["tau"] == 60


def test_ranking_mode_payload_records_the_bar_and_the_tie_convention(tmp_path):
    profile, job, manifest = toy()
    pool = []
    for cid, projects in (("c", 2), ("d", 4), ("e", 6), ("f", 8)):
        member = load_profile(FIXTURES / "toy_profile.json").model_copy(deep=True)
        member.project_counts_by_topic["backend"] = projects
        pool.append((cid, member))
    outcome = run_ranking_mode(profile, job, manifest, pool, "c", N=3)

    payload = make_payload(
        outcome, mode="B", job=job, manifest=manifest, profile=profile,
        candidate_id="c", cv_sha256="deadbeef", explanation_hash="cafe",
        versions={},
    )
    assert payload["mode"] == "B" and "tau" not in payload
    assert payload["N"] == 3
    assert payload["bar"] == outcome.decision.threshold
    assert payload["rank"] == outcome.decision.rank
    assert payload["pool_size"] == 4
    assert "pessimistic" in payload["tie_convention"]
    assert payload["aggregate_line"] == "3 of 4 advanced in this pool"
    assert payload["explanation_text_hash"] == "cafe"

    append_record(payload, path=tmp_path / "audit.jsonl")
    assert verify_chain(tmp_path / "audit.jsonl") == (True, 1, None)
