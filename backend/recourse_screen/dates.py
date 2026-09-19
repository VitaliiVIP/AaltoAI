"""Deterministic date arithmetic shared by the extractor postprocess and the
synthetic sampler. All dates are (year, month) tuples or "YYYY-MM" strings.
Never uses the wall clock: callers pass `as_of`.
"""
from __future__ import annotations

import re
from typing import Iterable

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
PRESENT_WORDS = {"present", "current", "now", "ongoing", "today", "nyt", "nykyinen", "-", "–", "—"}


def ym_to_index(ym: str) -> int:
    """'YYYY-MM' -> absolute month index (year*12 + month-1)."""
    y, m = ym.split("-")
    return int(y) * 12 + int(m) - 1


def index_to_ym(i: int) -> str:
    return f"{i // 12:04d}-{i % 12 + 1:02d}"


def normalise_date(raw: str | None, as_of: str) -> tuple[str | None, str]:
    """Return ('YYYY-MM' | None, precision) with precision in month|year|unknown.
    'Mar 2022' -> ('2022-03','month'); '2022' -> ('2022-07','year');
    'present' -> (as_of[:7], 'month'); unparsable -> (None, 'unknown')."""
    if raw is None:
        return None, "unknown"
    s = str(raw).strip().lower().rstrip(".")
    if not s:
        return None, "unknown"
    if s in PRESENT_WORDS or s.startswith("present") or s.startswith("current"):
        return as_of[:7], "month"
    m = re.match(r"^(\d{4})-(\d{1,2})(?:-\d{1,2})?$", s)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}", "month"
    m = re.match(r"^(\d{1,2})[/.](\d{4})$", s)
    if m:
        return f"{int(m.group(2)):04d}-{int(m.group(1)):02d}", "month"
    m = re.match(r"^([a-z]+)\.?\s+(\d{4})$", s)
    if m and m.group(1)[:3] in MONTHS:
        return f"{int(m.group(2)):04d}-{MONTHS[m.group(1)[:3]]:02d}", "month"
    m = re.match(r"^(\d{4})\s+([a-z]+)$", s)
    if m and m.group(2)[:3] in MONTHS:
        return f"{int(m.group(1)):04d}-{MONTHS[m.group(2)[:3]]:02d}", "month"
    m = re.match(r"^(\d{4})$", s)
    if m:
        return f"{int(m.group(1)):04d}-07", "year"  # mid-year; error bar +-6 months
    return None, "unknown"


def interval_months(start_ym: str, end_ym: str) -> int:
    """Half-open [start, end) length in months, clamped at 0."""
    return max(0, ym_to_index(end_ym) - ym_to_index(start_ym))


def union_months(intervals: Iterable[tuple[str, str]]) -> int:
    """Total months covered by the union of half-open [start, end) intervals.
    Overlapping contracts count once (union, not sum)."""
    spans = sorted((ym_to_index(s), ym_to_index(e)) for s, e in intervals if s and e)
    total, cur_s, cur_e = 0, None, None
    for s, e in spans:
        if e <= s:
            continue
        if cur_e is None or s > cur_e:
            if cur_e is not None:
                total += cur_e - cur_s
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        total += cur_e - cur_s
    return total


def clamp_end(end_ym: str | None, as_of: str) -> str:
    """Ends after as_of are clamped to as_of (profile is 'as of' a frozen date)."""
    if end_ym is None or ym_to_index(end_ym) > ym_to_index(as_of[:7]):
        return as_of[:7]
    return end_ym
