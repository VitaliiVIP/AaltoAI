"""Derived boolean features computed from the manifest's `derived` rules.
Used by the extractor postprocess and re-run after a restatement so that
confirming e.g. skills.aws.held also flips derived.cloud_platform_held."""
from __future__ import annotations

from .schemas import Envelope, Manifest, Profile


def recompute_derived(profile: Profile, manifest: Manifest) -> Profile:
    for name, rule in manifest.derived.items():
        best: Envelope | None = None
        any_denied = False
        for path in rule.any_of:
            try:
                env = profile.resolve(path)
            except KeyError:
                continue
            if env.value is True and env.derivation not in ("absent", "denied"):
                if best is None or _rank(env) > _rank(best):
                    best = env
            elif env.derivation == "denied":
                any_denied = True
        if best is not None:
            profile.derived[name] = Envelope(value=True, derivation=best.derivation,
                                             confidence=best.confidence, evidence=list(best.evidence))
        elif any_denied:
            profile.derived[name] = Envelope(value=False, derivation="denied", confidence="medium")
        else:
            profile.derived[name] = Envelope(value=None, derivation="absent", confidence="low")
    return profile


def _rank(env: Envelope) -> int:
    order = {"restated": 4, "stated": 3, "computed": 2, "inferred": 1}
    return order.get(env.derivation, 0)
