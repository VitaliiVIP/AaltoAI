"""Code-owned text: fallback sentences, framing and disclosures.

The LLM never writes any of this. It writes one sentence per delta and nothing
else; the intro, the ordering, the mode-B lines, the immutable-blocker text and
the closing disclosures are all generated here so they cannot drift.

Template selection is driven by `derivation_of_current` (brief 5.2):
  absent              -> question form ("if you have it, add it")
  stated/computed/inferred -> instruction form, magnitude in raw units
  denied              -> instruction form acknowledging the CV said no
Immutable blockers are rendered as the manifest's disclosure, verbatim.
"""
from __future__ import annotations

from ..schemas import Sentence
from .whitelist import DeltaView, ExplanationInput

# --------------------------------------------------------------------------- #
# Small lexical helpers
# --------------------------------------------------------------------------- #

_LEVEL_WORDS: dict[str, str] = {
    "none": "a first formal qualification",
    "secondary": "secondary education",
    "vocational": "a vocational qualification",
    "bsc": "a bachelor's degree",
    "msc": "a master's degree",
    "phd": "a doctorate",
}

def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and float(value).is_integer():
        return int(value)
    return None


def _magnitude(d: DeltaView) -> int | None:
    """to - from in raw units, treating a missing `from` as zero."""
    to = _as_int(d.to)
    if to is None:
        return None
    frm = _as_int(d.from_) or 0
    return to - frm


def _count_word(n: int) -> str:
    words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
             7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}
    return words.get(n, str(n))


def _time_clause(d: DeltaView, lead: str = "typically takes about") -> str:
    """'typically takes about 3 months', or '' when the manifest has no figure."""
    if d.typical_time_months is None:
        return ""
    n = d.typical_time_months
    unit = "month" if n == 1 else "months"
    return f"{lead} {n} {unit}"


def _level_phrase(d: DeltaView) -> str:
    """Render the target of a `level` delta in words the candidate can act on."""
    if isinstance(d.to, str):
        return _LEVEL_WORDS.get(d.to.lower(), f"a {d.to} qualification")
    n = _as_int(d.to)
    if n is not None:
        return f"{d.candidate_phrase} to level {n}"
    return d.candidate_phrase


# --------------------------------------------------------------------------- #
# Per-delta fallback sentences
# --------------------------------------------------------------------------- #

def fallback_sentence(d: DeltaView) -> str:
    """Stiff-but-true prose for one delta. Always passes the checker."""
    if d.derivation_of_current == "absent":
        return _absent_sentence(d)
    if d.derivation_of_current == "denied":
        return _denied_sentence(d)
    return _instruction_sentence(d)


def _absent_sentence(d: DeltaView) -> str:
    """Question form: the CV did not mention it, so never assert the person lacks it."""
    head = f"Your CV did not mention {d.candidate_phrase} — if you have it, add it to your CV"
    tail = _time_clause(d, lead="building it typically takes about")
    if tail:
        return f"{head}; if not, {tail}."
    return f"{head}; if not, this is one of the things the screen looks for."


def _denied_sentence(d: DeltaView) -> str:
    """The CV positively ruled this out, so instruct without contradicting it."""
    head = f"Your CV said you do not have {d.candidate_phrase}, so gaining it is one way to close this gap"
    tail = _time_clause(d)
    if tail:
        return f"{head}; it {tail}."
    return f"{head}."


def _instruction_sentence(d: DeltaView) -> str:
    """stated / computed / inferred: a concrete step, magnitude in raw units."""
    tail = _time_clause(d)
    mag = _magnitude(d)

    if d.unit == "months":
        n = mag if mag is not None else 0
        unit = "month" if n == 1 else "months"
        return f"Add about {n} more {unit} of {d.candidate_phrase}."

    if d.unit == "projects":
        n = mag if mag is not None else 1
        if n == 1:
            return (f"Add one more to your {d.candidate_phrase} — something you can "
                    f"describe and link.")
        return (f"Add {_count_word(n)} more to your {d.candidate_phrase} — work you can "
                f"describe and link.")

    if d.unit == "boolean":
        body = f"Gain {d.candidate_phrase}"
        return f"{body}; it {tail}." if tail else f"{body}."

    if d.unit == "level":
        body = f"Complete {_level_phrase(d)}"
        return f"{body}; it {tail}." if tail else f"{body}."

    body = f"Move {d.candidate_phrase} to {d.to}"
    return f"{body}; it {tail}." if tail else f"{body}."


def full_fallback(input: ExplanationInput) -> list[Sentence]:
    """One code-generated sentence per delta, in input order."""
    return [Sentence(delta_id=d.delta_id, sentence=fallback_sentence(d)) for d in input.deltas]


# --------------------------------------------------------------------------- #
# Framing
# --------------------------------------------------------------------------- #
#
# Two paragraphs, in the voice of an actual letter rather than a report:
# the outcome, then what stood out. Everything a route/blocker/no-feasible-path
# block used to spell out in its own section (route ranks, the full five-line
# disclosure) now rides along as a clause instead of a block -- the in-app
# "Why this match?" panel is where a recruiter gets the per-delta detail; the
# email only ever needed the cheapest path and the two disclaimers that actually
# carry legal weight (guidance-not-a-promise, the right to a human review).

HUMAN_REVIEW_LINE = "reply to this message to request a human review"


def _paragraph1(input: ExplanationInput) -> str:
    if input.outcome == "advanced":
        head = "Good news — your application moved forward to the next stage of this role."
    else:
        head = "Unfortunately, your application did not move forward at this stage."
    sentences = [
        head,
        "An automated screen compared your profile against the requirements this "
        "employer configured for this role; no person read your CV at this step.",
    ]
    if input.mode == "B" and input.rank is not None and input.pool_size is not None:
        line = f"You placed {input.rank} of {input.pool_size} in this pool."
        if input.slots_n is not None:
            line += f" {input.slots_n} of {input.pool_size} advanced."
        sentences.append(line)
    return " ".join(sentences)


def _weaknesses(input: ExplanationInput, by_id: dict[str, str]) -> str | None:
    """The single cheapest sufficient route's sentences, as flowing prose.
    `None` when there is nothing to report (an already-advanced candidate, or
    a not-advanced one with no route and no blocker -- shouldn't happen, but
    `frame` still needs a sane fallback)."""
    route_ids = input.route_ids()
    if not route_ids:
        return None
    deltas = input.deltas_for_route(route_ids[0])
    return " ".join(by_id.get(d.delta_id) or fallback_sentence(d) for d in deltas)


def _paragraph2(input: ExplanationInput, sentences: list[Sentence]) -> str:
    by_id = {s.delta_id: s.sentence for s in sentences}
    closing = f"You can ask for a person to review this decision — {HUMAN_REVIEW_LINE}."

    if input.immutable_blockers:
        fixed = " ".join(b.disclosure for b in input.immutable_blockers)
        return (
            f"One requirement for this role is fixed and no action on your part can "
            f"change it: {fixed} This is guidance, not a promise. {closing}"
        )

    weak = _weaknesses(input, by_id)

    if input.no_feasible_path:
        lead = (
            "Within the time window this screen looks ahead over, we did not find any "
            "combination of changes that would have changed this outcome."
        )
        if weak:
            return (
                f"{lead} The furthest progress we could map: {weak} On their own these "
                f"would not have changed this decision. That is a limit of what an "
                f"automated screen can work out, not a final word on you. {closing}"
            )
        return (
            f"{lead} That is a limit of what an automated screen can work out, not a "
            f"final word on you. {closing}"
        )

    if weak:
        return (
            f"Here is what stood out against this role's requirements. {weak} This is "
            f"guidance, not a promise — other changes could also have been enough, and "
            f"the timelines given are typical, not exact. {closing}"
        )

    return closing


def frame(input: ExplanationInput, sentences: list[Sentence]) -> str:
    """Two paragraphs: the outcome, then what stood out (or the fixed reason,
    when one applies)."""
    return f"{_paragraph1(input)}\n\n{_paragraph2(input, sentences)}"
