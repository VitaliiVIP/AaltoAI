"""The single result object both modes return and the API/explainer consume."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..schemas import (
    Decision,
    FeatureContribution,
    FeatureVector,
    ImmutableBlocker,
    NoFeasiblePath,
    Route,
)


@dataclass
class RecourseOutcome:
    feature_vector: FeatureVector
    decision: Decision
    contributions: list[FeatureContribution]
    routes: list[Route]
    immutable_blockers: list[ImmutableBlocker]
    no_feasible_path: NoFeasiblePath | None
    aggregate_line: str | None = None  # mode B only, e.g. "3 of 13 advanced in this pool"
    assertions: dict[str, bool] = field(default_factory=dict)
