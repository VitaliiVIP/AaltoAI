"""Job authoring: what a recruiter can change, and the rails around it.

The split mirrors the two-layer design. A *manifest* says what a feature is and
how it can move — engineering and domain expertise, edited in a text editor by
someone who knows what a causal constraint is. A *job* says what this role is
worth — an employer value judgement, and the only thing this package lets anyone
change.

- :mod:`.catalogue` — the manifest projected into the vocabulary HR picks from
- :mod:`.budget`    — snapping a point allocation onto something the scorer can represent
- :mod:`.store`     — the editable spec, its preflight, and writing it back as YAML
- :mod:`.draft`     — a first draft from a job ad (the only LLM in here)
"""
from __future__ import annotations

from .budget import normalise, snap
from .catalogue import catalogue_for, default_knockout, knockout_for
from .store import (
    JobSpec,
    ScoreLine,
    build,
    current_spec,
    preflight,
    save,
    spec_from_job,
)

__all__ = [
    "JobSpec",
    "ScoreLine",
    "build",
    "catalogue_for",
    "current_spec",
    "default_knockout",
    "knockout_for",
    "normalise",
    "preflight",
    "save",
    "snap",
    "spec_from_job",
]
