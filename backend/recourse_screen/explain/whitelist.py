"""The whitelist boundary for LLM #2.

Everything the explanation model is allowed to see lives in `ExplanationInput`.
Nothing else crosses: not the CV, not the weights, not the threshold, not the
score, not other candidates. See research/notes/cv_parsing_and_llm_brief.md 5.1.

`build_explanation_input` is the only sanctioned way to construct one from the
scoring/recourse outputs, so the projection is auditable in one place.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..schemas import (
    Actionability,
    Decision,
    Derivation,
    Delta,
    ImmutableBlocker,
    NoFeasiblePath,
    Route,
)


class DeltaView(BaseModel):
    """One minimal change, stripped of solver internals (no steps, no cost)."""

    model_config = ConfigDict(populate_by_name=True)

    delta_id: str
    field: str
    # `from` is a Python keyword; the alias keeps the wire/JSON name from 5.1.
    from_: Any = Field(default=None, alias="from")
    to: Any = None
    unit: str
    derivation_of_current: Derivation
    candidate_phrase: str
    typical_time_months: int | None = None
    actionability: Actionability
    route_id: str

    @classmethod
    def from_delta(cls, delta: Delta, route_id: str) -> "DeltaView":
        return cls(
            delta_id=delta.delta_id,
            field=delta.field,
            from_=delta.from_value,
            to=delta.to_value,
            unit=delta.unit,
            derivation_of_current=delta.derivation_of_current,
            candidate_phrase=delta.candidate_phrase,
            typical_time_months=delta.typical_time_months,
            actionability=delta.actionability,
            route_id=route_id,
        )


class BlockerView(BaseModel):
    """An immutable blocker, reduced to the manifest's fixed disclosure text."""

    field: str
    disclosure: str


class ExplanationInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    outcome: Literal["not_advanced", "advanced"]
    deltas: list[DeltaView] = Field(default_factory=list)
    immutable_blockers: list[BlockerView] = Field(default_factory=list)
    flip_test_passed: bool = False
    as_of: str
    model_version: str
    mode: Literal["A", "B"] = "A"

    # Mode B only. None in mode A.
    rank: int | None = None
    pool_size: int | None = None
    slots_n: int | None = None
    route_ranks: dict[str, int] = Field(default_factory=dict)

    # No feasible path within the horizon. Deliberately carries no reason string
    # and no gap figure: both are scoring internals. `partial_route_id` points at
    # the route in `deltas` that represents partial progress, when one exists.
    no_feasible_path: bool = False
    partial_route_id: str | None = None

    # ---- helpers used by the templates and the checker ------------------- #
    def route_ids(self) -> list[str]:
        """Route ids in first-appearance order."""
        seen: list[str] = []
        for d in self.deltas:
            if d.route_id not in seen:
                seen.append(d.route_id)
        return seen

    def deltas_for_route(self, route_id: str) -> list[DeltaView]:
        return [d for d in self.deltas if d.route_id == route_id]

    def delta_by_id(self, delta_id: str) -> DeltaView | None:
        return next((d for d in self.deltas if d.delta_id == delta_id), None)

    def to_prompt_json(self) -> str:
        """The exact bytes handed to the model. `by_alias` restores `from`."""
        return self.model_dump_json(by_alias=True, indent=1, exclude_none=False)


def build_explanation_input(
    *,
    decision: Decision,
    routes: list[Route],
    immutable_blockers: list[ImmutableBlocker],
    no_feasible_path: NoFeasiblePath | None,
    as_of: str,
    model_version: str,
) -> ExplanationInput:
    """Project the screening result down to the whitelisted object.

    When there are no routes but a `NoFeasiblePath` carries partial progress,
    that partial route's deltas are used so the candidate still sees concrete
    steps; `no_feasible_path` then tells the framing layer not to claim a flip.
    """
    partial_route_id: str | None = None
    source_routes = list(routes)
    if not source_routes and no_feasible_path is not None and no_feasible_path.partial_progress:
        source_routes = [no_feasible_path.partial_progress]
        partial_route_id = no_feasible_path.partial_progress.route_id

    deltas = [
        DeltaView.from_delta(d, route.route_id)
        for route in source_routes
        for d in route.deltas
    ]

    flip = bool(routes) and all(r.flip_test_passed for r in routes)

    return ExplanationInput(
        outcome="advanced" if decision.passed else "not_advanced",
        deltas=deltas,
        immutable_blockers=[
            BlockerView(field=b.field, disclosure=b.disclosure) for b in immutable_blockers
        ],
        flip_test_passed=flip,
        as_of=as_of,
        model_version=model_version,
        mode=decision.mode,
        rank=decision.rank if decision.mode == "B" else None,
        pool_size=decision.pool_size if decision.mode == "B" else None,
        slots_n=decision.slots_n if decision.mode == "B" else None,
        route_ranks={r.route_id: r.rank for r in source_routes if r.rank is not None},
        no_feasible_path=no_feasible_path is not None,
        partial_route_id=partial_route_id,
    )
