"""Code-owned text: fallback sentences, route labels, framing and disclosures.

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

_ROUTE_LABELS: dict[str, str] = {
    "build": "build",
    "certify": "certify",
    "deepen": "deepen",
    "wait": "wait",
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
    head = (f"Your CV did not mention {d.candidate_phrase} — if you have it, add it "
            f"and ask us to re-run the screen")
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
# Route labelling
# --------------------------------------------------------------------------- #

def _delta_category(d: DeltaView) -> str:
    field = d.field
    if field.startswith("certifications.") or field == "education.highest_level":
        return "certify"
    if d.unit == "months":
        return "wait" if field.startswith("experience.") else "deepen"
    if d.unit == "level":
        return "deepen"
    return "build"  # boolean, projects and anything unrecognised


def route_label(deltas: list[DeltaView]) -> str:
    """Label a route by its dominant delta unit; ties go to the first delta."""
    if not deltas:
        return "build"
    counts: dict[str, int] = {}
    order: list[str] = []
    for d in deltas:
        c = _delta_category(d)
        if c not in counts:
            counts[c] = 0
            order.append(c)
        counts[c] += 1
    best = max(order, key=lambda c: (counts[c], -order.index(c)))
    return _ROUTE_LABELS.get(best, "build")


# --------------------------------------------------------------------------- #
# Framing
# --------------------------------------------------------------------------- #

HUMAN_REVIEW_LINE = "reply to this message to request a human review"


def _intro(input: ExplanationInput) -> list[str]:
    if input.outcome == "advanced":
        head = "Your application moved forward to the next stage of this role."
    else:
        head = "Your application did not move forward at this stage."
    lines = [
        head,
        "An automated screen compared your profile against the requirements this "
        "employer configured for this role. No person read your CV at this step.",
    ]
    if input.mode == "B" and input.rank is not None and input.pool_size is not None:
        line = f"You placed {input.rank} of {input.pool_size} in this pool."
        if input.slots_n is not None:
            line += f" {input.slots_n} of {input.pool_size} advanced."
        lines.append(line)
    return lines


def _route_block(input: ExplanationInput, route_id: str, index: int,
                 by_id: dict[str, str]) -> list[str]:
    deltas = input.deltas_for_route(route_id)
    label = route_label(deltas)
    lines = [f"Route {index} ({label}):"]
    for d in deltas:
        text = by_id.get(d.delta_id) or fallback_sentence(d)
        lines.append(f"- {text}")
    rank = input.route_ranks.get(route_id)
    if input.mode == "B" and rank is not None:
        lines.append(f"  This route would have placed you around rank {rank} in this pool.")
    return lines


def _no_feasible_path_block(input: ExplanationInput) -> list[str]:
    has_partial = bool(input.deltas)
    lines = [
        "Within the time window this screen looks ahead over, we did not find any "
        "combination of changes that would have changed the outcome for this role.",
    ]
    if has_partial:
        lines.append(
            "The steps above are the furthest progress we could map. They are real "
            "progress, but on their own they would not have changed this decision."
        )
    lines.append(
        f"That is a limit of what an automated screen can work out, not a final word "
        f"on you: {HUMAN_REVIEW_LINE}, and a person will look at this in full."
    )
    return lines


def _blocker_block(input: ExplanationInput) -> list[str]:
    lines = ["One requirement for this role is fixed and no action on your part can change it:"]
    for b in input.immutable_blockers:
        lines.append(f"- {b.disclosure}")
    return lines


def _disclosures(input: ExplanationInput) -> list[str]:
    parts = [
        "This is guidance, not a promise.",
    ]
    if input.deltas and not input.no_feasible_path:
        parts.append(
            "Each route above is one sufficient path, not the only one; other "
            "combinations of changes would also have been enough, and making these "
            "changes does not guarantee any outcome."
        )
    parts.append(
        "Any times given are what these steps typically take, not what they will take for you."
    )
    parts.append(
        f"This reflects the screen as it ran on {input.as_of} under model version "
        f"{input.model_version}."
    )
    parts.append(
        "Role requirements and the group of people applying both change over time, so "
        "the same profile can be read differently later."
    )
    parts.append(
        f"You can have a person review this decision: {HUMAN_REVIEW_LINE}."
    )
    return [" ".join(parts)]


def frame(input: ExplanationInput, sentences: list[Sentence]) -> str:
    """Assemble the final candidate-facing text around the per-delta sentences."""
    by_id = {s.delta_id: s.sentence for s in sentences}
    blocks: list[str] = ["\n".join(_intro(input))]

    route_ids = input.route_ids()
    if route_ids and not input.no_feasible_path:
        if len(route_ids) == 1:
            blocks.append("Here is what would have been enough:")
        else:
            blocks.append(
                "Here are separate routes, each of which on its own would have been enough:"
            )
    elif route_ids and input.no_feasible_path:
        blocks.append("Here is the progress we could map for you:")

    for i, rid in enumerate(route_ids, start=1):
        blocks.append("\n".join(_route_block(input, rid, i, by_id)))

    if input.no_feasible_path:
        blocks.append("\n".join(_no_feasible_path_block(input)))

    if input.immutable_blockers:
        blocks.append("\n".join(_blocker_block(input)))

    blocks.extend(_disclosures(input))
    return "\n\n".join(blocks)
