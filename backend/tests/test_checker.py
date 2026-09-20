"""The checker must catch the five failures that would actually hurt someone:
a dropped delta, a duplicated one, an invented number, a comparative claim and
protected-attribute language.
"""
from __future__ import annotations

from recourse_screen.explain.checker import allowed_numbers, check, numerals_in
from recourse_screen.schemas import Sentence

from tests.test_templates import ABSENT_BOOL, STATED_MONTHS, make_input

INPUT = make_input([ABSENT_BOOL, STATED_MONTHS])

GOOD = [
    Sentence(delta_id="d1", sentence=(
        "Your CV did not mention hands-on Kubernetes experience — if you have it, add it "
        "to your CV; otherwise it takes most people about 4 months.")),
    Sentence(delta_id="d2", sentence=(
        "Add about 6 more months of professional backend engineering experience.")),
]


def test_clean_sentences_pass():
    assert check(GOOD, INPUT) == []


def test_missing_delta_is_caught():
    failures = check(GOOD[:1], INPUT)
    assert "missing_delta:d2" in failures


def test_duplicate_delta_is_caught():
    dupe = GOOD + [Sentence(delta_id="d1", sentence="Add it to your CV.")]
    assert "duplicate_delta:d1" in check(dupe, INPUT)


def test_extra_delta_id_is_caught():
    extra = GOOD + [Sentence(delta_id="d9", sentence="Learn something else entirely.")]
    assert "unknown_delta:d9" in check(extra, INPUT)


def test_invented_number_is_caught():
    bad = [GOOD[0], Sentence(delta_id="d2", sentence=(
        "Add about 6 more months of backend experience to reach the 60 points this role needs."))]
    assert "invented_number:d2:60" in check(bad, INPUT)


def test_spelled_out_invented_number_is_caught():
    bad = [Sentence(delta_id="d1", sentence=(
        "Your CV did not mention Kubernetes; add it, or expect about nine months to learn it.")),
        GOOD[1]]
    assert "invented_number:d1:9" in check(bad, INPUT)


def test_months_to_years_conversion_is_allowed():
    d = STATED_MONTHS.model_copy(update={"typical_time_months": 24})
    input = make_input([d])
    ok = [Sentence(delta_id="d2", sentence=(
        "Add about 6 more months of backend experience; people often take 2 years over this."))]
    assert check(ok, input) == []


def test_banned_lexicon_is_caught():
    bad = [GOOD[0], Sentence(delta_id="d2", sentence=(
        "We preferred applicants with more backend experience, so add about 6 more months."))]
    failures = check(bad, INPUT)
    assert "banned_phrase:d2:we preferred" in failures


def test_guarantee_language_is_caught():
    bad = [GOOD[0], Sentence(delta_id="d2", sentence=(
        "Add about 6 more months of backend experience and you will get an interview."))]
    failures = check(bad, INPUT)
    assert "banned_phrase:d2:will get" in failures
    assert "banned_phrase:d2:guarantee" not in failures


def test_protected_term_is_caught():
    bad = [GOOD[0], Sentence(delta_id="d2", sentence=(
        "At your age, about 6 more months of backend experience is a realistic step."))]
    assert "protected_term:d2:age" in check(bad, INPUT)


def test_protected_scan_does_not_fire_on_ordinary_words():
    ok = [Sentence(delta_id="d1", sentence=(
        "Your CV did not mention Kubernetes — if you manage clusters in any language, "
        "add it to your CV.")),
        Sentence(delta_id="d2", sentence=(
            "Add about 6 more months of backend experience; hold onto the dates you already gave."))]
    assert check(ok, INPUT) == []


def test_overlong_sentence_is_caught():
    long = " ".join(["word"] * 50) + "."
    bad = [GOOD[0], Sentence(delta_id="d2", sentence=long)]
    assert any(f.startswith("too_long:d2:") for f in check(bad, INPUT))


def test_flip_flag_must_be_true_when_there_are_deltas():
    input = make_input([ABSENT_BOOL, STATED_MONTHS], flip_test_passed=False)
    assert "flip_flag_false" in check(GOOD, input)


def test_flip_flag_is_not_required_on_a_partial_progress_route():
    input = make_input([ABSENT_BOOL, STATED_MONTHS], flip_test_passed=False,
                       no_feasible_path=True, partial_route_id="r1")
    assert "flip_flag_false" not in check(GOOD, input)


def test_allowed_numbers_covers_from_to_difference_and_time():
    assert allowed_numbers(STATED_MONTHS) == {18, 24, 6, 2}  # 24 months == 2 years
    assert allowed_numbers(ABSENT_BOOL) == {4}  # booleans contribute no magnitude


def test_numerals_in_reads_digits_and_words():
    assert numerals_in("about 3 months, or three at a push") == {3}
    assert numerals_in("no numbers here") == set()
