"""Turning a rough point allocation into one the scorer can actually represent.

A criterion worth ``points`` at full marks, reached in ``cap`` solver steps, is
worth ``points / cap`` per step, and that has to be a whole number or the budget
the employer published would not be the budget the engine applies. Rather than
round behind the employer's back, everything HR types goes through
:func:`normalise` first, which snaps each figure onto a realisable value and then
settles the remainder so the column adds up to exactly 100.

The snapping is deliberately done here and not in the browser: the same rules
have to hold for a config drafted from a job ad, and a second implementation in
TypeScript would be a second set of rounding bugs.
"""
from __future__ import annotations

from ..schemas import BUDGET_TOTAL, JobTemplate, Manifest

__all__ = ["BUDGET_TOTAL", "caps_for", "normalise", "snap"]


def caps_for(job: JobTemplate, manifest: Manifest) -> dict[str, int]:
    """path -> full-marks cap in steps, for every criterion the job scores."""
    return {path: max(1, job.cap_of(path, manifest)) for path in job.score}


def snap(points: int, cap: int) -> int:
    """The nearest number of points a criterion with this cap can actually be worth."""
    cap = max(1, cap)
    if points <= 0:
        return 0
    return max(cap, round(points / cap) * cap)


def normalise(
    requested: dict[str, int], caps: dict[str, int], total: int = BUDGET_TOTAL
) -> dict[str, int]:
    """Snap every figure, then spread the remainder until the budget sums to ``total``.

    The remainder is settled one cap-unit at a time, round-robin over the
    finest-grained criteria first, so no single line silently absorbs the whole
    correction. A criterion set to zero stays at zero — that is HR dropping it,
    not a rounding artefact — and is left out of the result.

    Raises:
        ValueError: the remainder cannot be settled, which happens only when
            every criterion is coarser than what is left over (no cap-1 line to
            absorb it). The message names the shortfall so the caller can say
            something useful.
    """
    out = {path: snap(want, caps.get(path, 1)) for path, want in requested.items()}
    live = [p for p, v in out.items() if v > 0]
    if not live:
        raise ValueError("a job needs at least one scored criterion")

    # Finest granularity first: a cap-1 line can absorb a single point, a cap-8
    # line moves in jumps of 8 and should only be touched as a last resort.
    order = sorted(live, key=lambda p: (max(1, caps.get(p, 1)), -out[p]))
    i = 0
    stalled = 0
    while (remainder := total - sum(out.values())) != 0 and stalled < len(order):
        path = order[i % len(order)]
        i += 1
        cap = max(1, caps.get(path, 1))
        up = remainder > 0
        if cap > abs(remainder) or (not up and out[path] - cap <= 0):
            stalled += 1
            continue
        out[path] += cap if up else -cap
        stalled = 0

    remainder = total - sum(out.values())
    if remainder:
        raise ValueError(
            f"cannot make this budget add up to {total}: {abs(remainder)} point(s) "
            f"{'unallocated' if remainder > 0 else 'over'} and no criterion is fine-grained "
            "enough to absorb the difference; add or adjust a yes/no criterion"
        )
    return {p: v for p, v in out.items() if v > 0}
