"""The checker that runs on every generated explanation before anything is shown.

Returns a list of failure codes; empty means the text may ship. Nothing here
calls an LLM: these are the cheap, deterministic checks from brief 5.3 that
catch the damaging failures (invented numbers, comparative claims, protected
terms, dropped or duplicated deltas).

Failure codes are stable strings so they can be logged, asserted on in tests,
and fed back to the model on the single regeneration attempt.
"""
from __future__ import annotations

import re

from ..schemas import Sentence
from .whitelist import DeltaView, ExplanationInput

MAX_WORDS = 45

# Comparative or causal claims the system cannot support (brief 5.3).
BANNED_PHRASES: list[str] = [
    "better candidates",
    "stronger applicants",
    "we preferred",
    "not qualified",
    "unfortunately your profile",
    "your background suggests",
    "guarantee",
    "will get",
    "rejected because",
]

# Protected-attribute language. Whole-word patterns for the short words so
# "manage"/"hold"/"language" do not trip the scan; stems for the rest.
PROTECTED_PATTERNS: list[tuple[str, str]] = [
    ("age", r"\bages?\b"),
    ("gender", r"\bgenders?\b"),
    ("nationality", r"\bnationalit(?:y|ies)\b"),
    ("married", r"\bmarried\b"),
    ("religion", r"\breligion\b"),
    ("disab", r"disab"),
    ("pregnan", r"pregnan"),
    ("years old", r"\byears?\s+old\b"),
    ("young", r"\byoung\w*\b"),
    ("old", r"\bold(?:er|est)?\b"),
]

_NUMBER_WORDS: dict[str, int] = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}

# Words that turn a spelled-out number into a quantity claim.
_QUANTIFIED: set[str] = {
    "month", "months", "year", "years", "project", "projects", "level", "levels",
    "more", "additional", "further", "extra",
}

_DIGITS_RE = re.compile(r"\d+")
_WORD_RE = re.compile(r"[a-z]+")


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and float(value).is_integer():
        return int(value)
    return None


def allowed_numbers(d: DeltaView) -> set[int]:
    """Integers a sentence about this delta may legitimately contain.

    from, to, to-from, typical_time_months, plus the whole-year form of each
    (12 months may be written as '1 year'). Booleans and level names contribute
    nothing: there is no number to quote.
    """
    base: set[int] = set()
    frm, to = _as_int(d.from_), _as_int(d.to)
    for v in (frm, to, d.typical_time_months):
        n = _as_int(v)
        if n is not None:
            base.add(n)
    if to is not None:
        base.add(to - (frm or 0))
    out = set(base)
    for n in base:
        if n % 12 == 0:
            out.add(n // 12)
    return out


def numerals_in(text: str) -> set[int]:
    """Every integer the sentence asserts.

    Digits always count. A spelled-out number counts only when it quantifies
    something ("six months", "one more"), so that "one way to close this gap"
    is prose rather than a claim about a magnitude.
    """
    found = {int(m) for m in _DIGITS_RE.findall(text)}
    words = _WORD_RE.findall(text.lower())
    for i, w in enumerate(words):
        if w in _NUMBER_WORDS and i + 1 < len(words) and words[i + 1] in _QUANTIFIED:
            found.add(_NUMBER_WORDS[w])
    return found


def check(sentences: list[Sentence], input: ExplanationInput) -> list[str]:
    """Return failure codes. Empty list means the sentences may be framed and shown."""
    failures: list[str] = []

    # 1. Coverage and injectivity of delta ids.
    expected = [d.delta_id for d in input.deltas]
    seen: dict[str, int] = {}
    for s in sentences:
        seen[s.delta_id] = seen.get(s.delta_id, 0) + 1
    for did in expected:
        if did not in seen:
            failures.append(f"missing_delta:{did}")
    for did, n in seen.items():
        if did not in expected:
            failures.append(f"unknown_delta:{did}")
        elif n > 1:
            failures.append(f"duplicate_delta:{did}")

    # 2-5. Per-sentence content checks.
    for s in sentences:
        d = input.delta_by_id(s.delta_id)
        lower = s.sentence.lower()

        if d is not None:
            allowed = allowed_numbers(d)
            for n in sorted(numerals_in(s.sentence)):
                if n not in allowed:
                    failures.append(f"invented_number:{s.delta_id}:{n}")

        for phrase in BANNED_PHRASES:
            if phrase in lower:
                failures.append(f"banned_phrase:{s.delta_id}:{phrase}")

        for term, pattern in PROTECTED_PATTERNS:
            if re.search(pattern, lower):
                failures.append(f"protected_term:{s.delta_id}:{term}")

        words = len(s.sentence.split())
        if words > MAX_WORDS:
            failures.append(f"too_long:{s.delta_id}:{words}")

    # 6. Flip test. Claiming "this would have been enough" requires the flag,
    # except on a partial-progress route, which never claims a flip.
    if input.deltas and not input.no_feasible_path and not input.flip_test_passed:
        failures.append("flip_flag_false")

    return failures
