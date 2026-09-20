"""The authoring surface: the point budget, the catalogue, and writing a job back.

These are the rails that stop a recruiter-authored job from being wrong in a way
only the solver would notice.
"""
from pathlib import Path

import pytest
import yaml

from recourse_screen.authoring import budget, catalogue_for, store
from recourse_screen.authoring.catalogue import default_knockout
from recourse_screen.loaders import load_job, load_manifest, manifest_for_job
from recourse_screen.schemas import BUDGET_TOTAL, JobTemplate, Manifest, ScoreTerm
from recourse_screen.score.scorer import max_score

FIXTURES = Path(__file__).parent / "fixtures"


# --------------------------------------------------------------------------- #
# The point budget
# --------------------------------------------------------------------------- #

def test_the_shipped_job_is_a_hundred_point_budget():
    job = load_job("data_scientist")
    manifest = manifest_for_job(job)
    assert sum(job.points_of(p, manifest) for p in job.score) == BUDGET_TOTAL
    # The whole reason for the budget: a score is a percentage of the job.
    assert max_score(job, manifest) == BUDGET_TOTAL


def test_points_become_per_step_weights():
    job = load_job("data_scientist")
    manifest = manifest_for_job(job)
    term = job.score["experience.data_months"]
    # 30 points spread over 10 six-month steps is 3 points per step.
    assert term.points == 30 and job.cap_of("experience.data_months", manifest) == 10
    assert term.weight == 3


def test_binding_is_idempotent():
    job = load_job("data_scientist").model_copy(deep=True)
    manifest = manifest_for_job(job)
    before = {p: t.weight for p, t in job.score.items()}
    job.bind(manifest).bind(manifest)
    assert {p: t.weight for p, t in job.score.items()} == before


def _spec_job(**score) -> JobTemplate:
    return JobTemplate(
        job_id="t", title="T", family="toy", manifest="toy_manifest.json",
        score={p: ScoreTerm(**v) for p, v in score.items()},
        mode={"A": {"threshold": 50}, "B": {}},
    )


def _toy_manifest() -> Manifest:
    return load_manifest(FIXTURES / "toy_manifest.json")


def test_a_budget_that_does_not_add_up_is_rejected():
    job = _spec_job(**{
        "skills.python.months": {"points": 40, "cap": 4},
        "skills.docker.held": {"points": 40},
    })
    with pytest.raises(ValueError, match="sums to 80, not 100"):
        job.bind(_toy_manifest())


def test_points_that_do_not_divide_into_steps_name_the_nearest_valid_values():
    job = _spec_job(**{
        "skills.python.months": {"points": 30, "cap": 4},
        "skills.docker.held": {"points": 70},
    })
    with pytest.raises(ValueError, match="does not divide into 4 steps"):
        job.bind(_toy_manifest())


def test_weight_and_points_cannot_both_be_authored():
    with pytest.raises(ValueError, match="not both"):
        ScoreTerm(weight=4, points=32, cap=8)


def test_a_weight_authored_job_still_loads():
    """The toy fixture predates the budget and must keep working untouched."""
    job = load_job(FIXTURES / "toy_job.yaml")
    assert not job.uses_budget
    assert job.score["skills.python.months"].weight == 6


# --------------------------------------------------------------------------- #
# Snapping
# --------------------------------------------------------------------------- #

def test_snap_moves_to_the_nearest_representable_value():
    assert budget.snap(30, 8) == 32
    assert budget.snap(27, 8) == 24
    assert budget.snap(7, 1) == 7
    assert budget.snap(0, 8) == 0
    # A criterion worth something can never snap to nothing.
    assert budget.snap(1, 8) == 8


def test_normalise_settles_the_remainder_on_the_finest_criteria():
    caps = {"coarse": 8, "a": 1, "b": 1, "c": 1}
    out = budget.normalise({"coarse": 30, "a": 30, "b": 20, "c": 21}, caps)
    assert sum(out.values()) == BUDGET_TOTAL
    assert out["coarse"] == 32  # snapped, then left alone
    # The three point-granular lines absorbed the correction between them.
    assert sorted(out[k] for k in ("a", "b", "c")) == sorted([29, 20, 19])


def test_normalise_drops_criteria_set_to_zero():
    out = budget.normalise({"a": 60, "b": 40, "c": 0}, {"a": 1, "b": 1, "c": 1})
    assert "c" not in out and sum(out.values()) == BUDGET_TOTAL


def test_normalise_explains_itself_when_nothing_can_absorb_the_remainder():
    with pytest.raises(ValueError, match="fine-grained"):
        budget.normalise({"a": 30, "b": 30}, {"a": 8, "b": 8})


# --------------------------------------------------------------------------- #
# Catalogue
# --------------------------------------------------------------------------- #

def test_catalogue_offers_every_usable_feature_and_names_the_refused_ones():
    job = load_job("data_scientist")
    manifest = manifest_for_job(job)
    cat = catalogue_for(manifest, job)

    offered = {f["path"] for f in cat["features"]}
    refused = {r["path"] for r in cat["protected_never_use"]}
    assert offered and refused == manifest.protected_paths()
    assert not offered & refused
    # Refusals carry the reason, not just the absence.
    assert all(r["reason"] for r in cat["protected_never_use"])


def test_catalogue_knockout_templates_parse_as_rules():
    from recourse_screen.schemas import Knockout

    manifest = load_manifest("data_science.json")
    for feature in catalogue_for(manifest)["features"]:
        template = feature["knockout_template"]
        if template is None:
            continue
        assert Knockout.parse(template).path == feature["path"]


def test_a_degree_knockout_defaults_to_the_middle_of_the_ladder_not_the_top():
    manifest = load_manifest("data_science.json")
    spec = manifest.features["education.highest_level"]
    assert default_knockout("education.highest_level", spec) == "education.highest_level >= bsc"


# --------------------------------------------------------------------------- #
# Round trip
# --------------------------------------------------------------------------- #

def test_a_job_survives_a_spec_round_trip():
    job = load_job("data_scientist")
    manifest = manifest_for_job(job)
    spec = store.spec_from_job(job, manifest)
    rebuilt, allocation = store.build(spec, manifest)

    assert allocation == {p: job.points_of(p, manifest) for p in job.score}
    assert {p: t.weight for p, t in rebuilt.score.items()} == {
        p: t.weight for p, t in job.score.items()
    }
    assert rebuilt.knockouts == job.knockouts
    assert rebuilt.mode.A.threshold == job.mode.A.threshold


def test_saving_writes_yaml_that_loads_back_identically(tmp_path, monkeypatch):
    from recourse_screen import config, loaders

    monkeypatch.setattr(config, "JOBS_DIR", tmp_path)
    job = load_job("data_scientist")
    spec = store.spec_from_job(job, manifest_for_job(job))
    spec.job_id = "round_trip"
    spec.title = "Round trip"

    path = store.save(spec)
    assert path == tmp_path / "round_trip.yaml"
    written = yaml.safe_load(path.read_text())
    assert sum(line["points"] for line in written["score"].values()) == BUDGET_TOTAL

    reloaded = loaders.load_job("round_trip")
    assert {p: t.weight for p, t in reloaded.score.items()} == {
        p: t.weight for p, t in job.score.items()
    }
    loaders.load_job.cache_clear()


def test_preflight_reports_a_threshold_nobody_can_reach():
    job = load_job("data_scientist")
    spec = store.spec_from_job(job, manifest_for_job(job))
    spec.threshold = 140
    report = store.preflight(spec)
    assert not report["ok"]
    assert any("above the whole budget" in p for p in report["problems"])


def test_preflight_refuses_to_score_a_protected_attribute():
    job = load_job("data_scientist")
    spec = store.spec_from_job(job, manifest_for_job(job))
    spec.score["education.graduation_year"] = store.ScoreLine(points=5)
    report = store.preflight(spec)
    assert not report["ok"]
    assert any("protected" in p for p in report["problems"])


# --------------------------------------------------------------------------- #
# Causal constraints now belong to the manifest
# --------------------------------------------------------------------------- #

def test_the_manifest_owns_the_causal_constraints():
    from recourse_screen.schemas import effective_dependencies

    job = load_job("data_scientist")
    manifest = manifest_for_job(job)
    assert job.dependencies == []  # moved out of the employer's file
    assert len(manifest.dependencies) == 2
    assert len(effective_dependencies(job, manifest)) == 2


def test_manifest_dependencies_still_constrain_the_solver():
    """A data pipeline cannot be credited without SQL, wherever the rule is written."""
    from recourse_screen import pipeline
    from recourse_screen.recourse.ranking_mode import run_ranking_mode

    job = load_job("data_scientist")
    manifest = manifest_for_job(job)
    pool = pipeline.load_pool()
    by_id = dict(pool)

    def outcome_routes(profile, job, manifest, pool, cid):
        return run_ranking_mode(profile, job, manifest, pool, cid).routes

    # Daniel lists SQLite and nothing else SQL-shaped, so the rule has to bite:
    # every route that credits him a data pipeline must credit SQL too.
    cid = "cv7_daniel_kwan"
    assert by_id[cid].resolve("derived.sql_held").value is not True
    bound = 0
    for route in outcome_routes(by_id[cid], job, manifest, pool, cid):
        moved = {d.field for d in route.deltas}
        if "derived.data_pipeline_held" in moved:
            bound += 1
            assert "derived.sql_held" in moved
    assert bound, "expected at least one route to touch the data pipeline"


def test_every_dependency_glosses_itself():
    manifest = load_manifest("data_science.json")
    for dep in manifest.parsed_dependencies:
        gloss = dep.gloss(manifest)
        assert gloss.endswith(".") and len(gloss.split()) > 4
        # The gloss names the feature in candidate language, not as a path.
        assert "x'[" not in gloss and "delta[" not in gloss


def test_an_ordinal_knockout_compares_on_the_ladder_not_alphabetically():
    from recourse_screen.schemas import Knockout

    manifest = load_manifest("data_science.json")
    spec = manifest.features["education.highest_level"]
    rule = Knockout.parse("education.highest_level >= bsc")
    assert rule.holds("msc", spec) and rule.holds("phd", spec)
    # "none" sorts after "bsc" as a string; it must not clear a degree requirement.
    assert not rule.holds("none", spec)
    assert not rule.holds("secondary", spec)
