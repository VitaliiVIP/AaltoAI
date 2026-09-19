"""End-to-end on the worked-example fixtures, no LLM, audit to a tmp path."""
from pathlib import Path

import pytest

from recourse_screen import config, pipeline
from recourse_screen.loaders import load_profile

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def tmp_audit(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "AUDIT_LOG_PATH", tmp_path / "audit.jsonl")
    yield


def test_threshold_mode_end_to_end():
    prof = load_profile(FIX / "toy_profile.json")
    res = pipeline.screen_profile(prof, candidate_id="toy", job_id=str(FIX / "toy_job.yaml"),
                                  mode="A", explain=False)
    assert res.decision.score == 47 and not res.decision.passed
    assert [r.cost for r in res.routes] == [16, 19, 21]
    assert all(r.flip_test_passed for r in res.routes)
    assert res.explanation is not None and res.explanation.fallback_used
    assert res.decision_id != "unaudited"
    from recourse_screen.audit.log import verify_chain
    ok, n, _ = verify_chain()
    assert ok and n == 1


def test_ranking_mode_end_to_end():
    prof = load_profile(FIX / "toy_profile.json")
    better = prof.model_copy(deep=True)
    better.skills["python"].months.value = 120  # 10 years -> +42 points
    pool = [("toy", prof), ("better1", better), ("better2", better.model_copy(deep=True))]
    res = pipeline.screen_profile(prof, candidate_id="toy", job_id=str(FIX / "toy_job.yaml"),
                                  mode="B", N=1, explain=False, pool=pool)
    assert res.decision.rank == 3 and res.decision.pool_size == 3 and not res.decision.passed
    assert res.aggregate_line
    for r in res.routes:
        assert r.rank is not None and r.rank <= 1
