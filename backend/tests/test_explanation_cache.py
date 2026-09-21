"""The API never spends a model call. Model-written sentences come from the
data/explanations cache or not at all; the live path needs `allow_live=True`,
which only scripts/cache_explanations.py passes."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from recourse_screen import config
from recourse_screen.api.app import app
from recourse_screen.explain.cache import cache_key, cache_path, load_cached, store_cached
from recourse_screen.explain.generate import explain_input
from recourse_screen.explain.verbaliser import SentencesOut
from recourse_screen.explain.whitelist import DeltaView, ExplanationInput
from recourse_screen.schemas import Sentence

from .test_templates import ABSENT_BOOL, STATED_MONTHS


@pytest.fixture(autouse=True)
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EXPLANATION_CACHE_DIR", tmp_path)
    return tmp_path


class ExplodingClient:
    """Stands in for anthropic.Anthropic: any call is a test failure."""

    class messages:  # noqa: N801 - mirrors the SDK's attribute
        @staticmethod
        def parse(**_kw):
            raise AssertionError("the model was called")


class CannedClient:
    """Returns a fixed SentencesOut, and counts how often it was asked."""

    def __init__(self, sentences: list[Sentence]):
        self.calls = 0
        outer = self

        class _Response:
            stop_reason = "end_turn"
            parsed_output = SentencesOut(sentences=sentences)

        class _Messages:
            @staticmethod
            def parse(**_kw):
                outer.calls += 1
                return _Response()

        self.messages = _Messages()


def _input(*deltas: DeltaView) -> ExplanationInput:
    return ExplanationInput(
        outcome="not_advanced", deltas=list(deltas), as_of="2026-09-19",
        model_version="ds-v1/scorer-v1", flip_test_passed=True,
    )


def _generate(input: ExplanationInput, **kw):
    return explain_input(input, **kw)


GOOD = [
    Sentence(delta_id="d1", sentence="If you have used a machine-learning framework, say so on your CV."),
    Sentence(delta_id="d2", sentence="Six more months of professional data science experience would cover this."),
]


def test_key_is_the_prompt_and_the_prompt_version(monkeypatch):
    a = _input(ABSENT_BOOL)
    before = cache_key(a)
    assert before == cache_key(_input(ABSENT_BOOL))
    assert before != cache_key(_input(ABSENT_BOOL, STATED_MONTHS))
    monkeypatch.setattr(config, "EXPLAIN_PROMPT_VERSION", "explain-v999")
    assert cache_key(a) != before


def test_round_trip(cache_dir):
    inp = _input(ABSENT_BOOL, STATED_MONTHS)
    path = store_cached(inp, GOOD, model_version="explain-v1/some-model")
    assert path == cache_path(cache_key(inp)) and path.parent == cache_dir
    assert load_cached(inp) == (GOOD, "explain-v1/some-model")
    assert load_cached(_input(ABSENT_BOOL)) is None


def test_miss_without_allow_live_is_a_template_and_no_call():
    exp = _generate(_input(ABSENT_BOOL, STATED_MONTHS), use_llm=True, client=ExplodingClient())
    assert exp.fallback_used is True
    assert exp.checks_passed is True
    assert exp.check_failures == []
    assert len(exp.sentences) == 2


def test_hit_serves_cached_sentences_without_a_call():
    inp = _input(ABSENT_BOOL, STATED_MONTHS)
    store_cached(inp, GOOD, model_version="explain-v1/older-model")
    exp = _generate(inp, use_llm=True, client=ExplodingClient())
    assert exp.fallback_used is False
    assert exp.sentences == GOOD
    assert exp.model_version == "explain-v1/older-model"
    assert GOOD[0].sentence in exp.text


def test_cached_sentences_are_rechecked_on_the_way_out():
    inp = _input(ABSENT_BOOL, STATED_MONTHS)
    bad = [Sentence(delta_id="d1", sentence="Add 17 more projects."),  # invented number
           Sentence(delta_id="d2", sentence="Six more months would cover this.")]
    store_cached(inp, bad, model_version="explain-v1/m")
    exp = _generate(inp, use_llm=True, client=ExplodingClient())
    assert exp.fallback_used is True
    assert exp.sentences != bad


def test_use_llm_false_ignores_the_cache():
    inp = _input(ABSENT_BOOL, STATED_MONTHS)
    store_cached(inp, GOOD, model_version="explain-v1/m")
    exp = _generate(inp, use_llm=False, client=ExplodingClient())
    assert exp.fallback_used is True


def test_allow_live_calls_once_and_fills_the_cache():
    inp = _input(ABSENT_BOOL, STATED_MONTHS)
    client = CannedClient(GOOD)
    first = _generate(inp, use_llm=True, allow_live=True, client=client)
    assert client.calls == 1
    assert first.fallback_used is False and first.sentences == GOOD
    assert json.loads(cache_path(cache_key(inp)).read_text())["sentences"][0]["delta_id"] == "d1"

    second = _generate(inp, use_llm=True, allow_live=True, client=client)
    assert client.calls == 1, "a cache hit must not call again, even when live is allowed"
    assert second.sentences == GOOD


def test_screen_explain_true_never_calls_the_model(monkeypatch):
    """The API passes `explain` through but never `allow_live_llm`."""
    import recourse_screen.explain.generate as gen

    monkeypatch.setattr(gen, "verbalise", lambda *a, **k: pytest.fail("live verbaliser reached"))
    res = TestClient(app).post("/screen", json={"candidate_id": "cv1_elina_korhonen", "mode": "A",
                                                "explain": True})
    assert res.status_code == 200
    body = res.json()
    if body["explanation"] is not None:
        assert body["explanation"]["checks_passed"] is True


@pytest.mark.parametrize("method,path", [
    ("post", "/extract"),
    ("post", "/jobs/draft"),
    ("get", "/"),
    ("get", "/static/index.html"),
    # Public site: nothing that sends mail or rewrites the shared pool or job.
    ("post", "/send-email"),
    ("delete", "/candidates/cv1_elina_korhonen"),
    ("post", "/jobs"),
])
def test_model_spending_state_changing_and_demo_page_routes_are_gone(method, path):
    res = getattr(TestClient(app), method)(path)
    assert res.status_code in (404, 405)


def test_screen_needs_a_pooled_candidate():
    client = TestClient(app)
    assert client.post("/screen", json={"cv_text": "Jane Doe, data scientist"}).status_code == 422
    assert client.post("/screen", json={"candidate_id": "nobody"}).status_code == 404
