"""The restatement channel: 'missing is not absent', made actionable.

Two halves:

- `restatement_hints` surfaces fields the screen did not find but that the
  candidate plausibly already has. Co-occurrence hints come first (Django on the
  CV makes SQL very likely), then every scored or knocked-out path the CV simply
  did not mention. Both are zero-cost: restating something you already did costs
  nothing but a click.
- `apply_confirmations` writes the candidate's answers back into a copy of the
  profile with derivation "restated", recomputes the derived booleans, and hands
  the new profile back. The caller re-runs scoring, recourse and explanation.

This doubles as the right-to-correct-data route (GDPR Art. 16), so it refuses
to touch immutable or protected paths: those are not data-entry mistakes.
"""
from __future__ import annotations

from .derived import recompute_derived
from .schemas import (
    Confirmation,
    Envelope,
    JobTemplate,
    Manifest,
    Profile,
    RestatementHint,
    SkillEntry,
)

NOT_MENTIONED = "not mentioned"


# --------------------------------------------------------------------------- #
# Hints
# --------------------------------------------------------------------------- #

def _job_paths(job: JobTemplate) -> set[str]:
    """Every profile path this job actually reads: scored terms plus knockouts."""
    paths = set(job.score.keys())
    for ko in job.parsed_knockouts:
        paths.add(ko.path)
    return paths


def _skill_matters(skill: str, job_paths: set[str], manifest: Manifest) -> bool:
    """True if confirming this skill could move something the job reads."""
    if f"skills.{skill}.held" in job_paths or f"skills.{skill}.months" in job_paths:
        return True
    for name, rule in manifest.derived.items():
        if f"derived.{name}" in job_paths and f"skills.{skill}.held" in rule.any_of:
            return True
    return False


def _phrase_for(path: str, manifest: Manifest, fallback: str) -> str:
    spec = manifest.features.get(path)
    if spec is not None:
        return spec.candidate_phrase
    return fallback


def _taxonomy_label(skill: str) -> str:
    try:
        from .loaders import load_taxonomy

        return load_taxonomy().label(skill)
    except Exception:  # missing or unreadable taxonomy must never break a screen
        return skill.replace("_", " ")


def _is_absent(profile: Profile, path: str) -> bool:
    """Absent means 'the CV did not say'. Denied is a positive no, and stays no."""
    try:
        env = profile.resolve(path)
    except KeyError:
        return False
    return env.derivation == "absent"


def confirmable_paths(manifest: Manifest) -> set[str]:
    """Paths a candidate may restate.

    Scored features that are not immutable or protected, plus every path feeding
    a `derived` rule. The second half matters: the manifest lists
    `derived.cloud_platform_held` as a feature but not the `skills.aws.held`
    that satisfies it, and "I have used AWS, it is just not on the page" is
    exactly the correction this channel exists for.
    """
    allowed = {
        p for p, f in manifest.features.items()
        if f.actionability not in ("immutable", "protected_never_use")
    }
    for rule in manifest.derived.values():
        allowed.update(rule.any_of)
    return allowed


def restatement_hints(profile: Profile, manifest: Manifest, job: JobTemplate) -> list[RestatementHint]:
    """Zero-cost things to confirm, most likely first.

    Ordering is the product: a candidate who sees "you listed Django, did you
    also use SQL?" answers it. A flat list of everything the screen missed is
    far less likely to be filled in.
    """
    job_paths = _job_paths(job)
    allowed = confirmable_paths(manifest)
    hints: dict[str, RestatementHint] = {}

    # 1. Co-occurrence: skills that almost always travel with a stated skill.
    for skill, entry in profile.skills.items():
        held = entry.held
        if held.value is not True or held.derivation in ("absent", "denied"):
            continue
        for likely in manifest.cooccurrence.get(skill, []):
            path = f"skills.{likely}.held"
            if path in hints or path not in allowed:
                continue
            if not _is_absent(profile, path):
                continue
            if not _skill_matters(likely, job_paths, manifest):
                continue
            hints[path] = RestatementHint(
                field=path,
                phrase=_phrase_for(path, manifest, _taxonomy_label(likely)),
                because_of=skill,
                zero_cost=True,
            )

    # 2. Everything else the job reads that the CV simply did not mention.
    for path in sorted(job_paths):
        if path in hints or path not in allowed:
            continue
        # Only boolean features can be confirmed with a tick; months/levels need a value.
        if manifest.features[path].type != "bool":
            continue
        if not _is_absent(profile, path):
            continue
        hints[path] = RestatementHint(
            field=path,
            phrase=_phrase_for(path, manifest, path),
            because_of=NOT_MENTIONED,
            zero_cost=True,
        )

    cooc = [h for h in hints.values() if h.because_of != NOT_MENTIONED]
    plain = [h for h in hints.values() if h.because_of == NOT_MENTIONED]
    return cooc + plain


# --------------------------------------------------------------------------- #
# Confirmations
# --------------------------------------------------------------------------- #

def apply_confirmations(
    profile: Profile,
    confirmations: list[Confirmation],
    manifest: Manifest,
) -> Profile:
    """Return a new profile with the confirmed values written as "restated".

    Raises ValueError for any path outside the manifest, or on an immutable or
    protected feature. Validation runs over the whole batch before anything is
    written, so a rejected confirmation never leaves a half-applied profile.
    """
    allowed = confirmable_paths(manifest)
    for c in confirmations:
        spec = manifest.features.get(c.path)
        if spec is not None and spec.actionability == "protected_never_use":
            raise ValueError(f"protected path, refusing to restate: {c.path}")
        if spec is not None and spec.actionability == "immutable":
            raise ValueError(f"immutable path, refusing to restate: {c.path}")
        if c.path not in allowed:
            raise ValueError(f"path is not restatable under this manifest: {c.path}")

    updated = profile.model_copy(deep=True)

    for c in confirmations:
        parts = c.path.split(".")
        if parts[0] == "skills" and len(parts) == 3:
            updated.skills.setdefault(parts[1], SkillEntry())
        updated.set_path(c.path, Envelope(value=c.value, derivation="restated", confidence="high"))

    recompute_derived(updated, manifest)

    # A directly confirmed derived boolean is the candidate's own statement and
    # outranks the recomputation, which would otherwise reset it to absent when
    # none of its any_of skills was confirmed individually.
    for c in confirmations:
        if c.path.startswith("derived."):
            updated.set_path(
                c.path, Envelope(value=c.value, derivation="restated", confidence="high")
            )

    return updated
