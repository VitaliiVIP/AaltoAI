"""Append-only, hash-chained decision log.

One JSON object per line. Each record's hash covers the previous record's hash, so
editing or removing any line breaks every hash after it and ``verify_chain`` reports
the first index that no longer checks out. This is the concrete answer to "what would
an auditor ask for", and it maps onto the EU AI Act Article 86 explanation right and
Colorado SB 26-189's adverse-decision explanation duty.

The timestamp here is the one place in the backend allowed to read the wall clock:
everything else is pinned to ``config.AS_OF`` so decisions stay replayable.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .. import config
from ..recourse.outcome import RecourseOutcome
from ..schemas import AuditRecord, JobTemplate, Manifest, Profile

GENESIS_HASH = "0" * 64


def canonical_json(obj: Any) -> str:
    """The exact byte string the hashes are taken over."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def record_hash(prev_hash: str, decision_id: str, timestamp: str, payload: dict) -> str:
    body = canonical_json(
        {"decision_id": decision_id, "timestamp": timestamp, "payload": payload}
    )
    return _sha256(prev_hash + body)


def _path(path: Path | None) -> Path:
    return Path(path) if path is not None else config.AUDIT_LOG_PATH


def read_records(path: Path | None = None) -> list[AuditRecord]:
    p = _path(path)
    if not p.exists():
        return []
    return [
        AuditRecord.model_validate_json(line)
        for line in p.read_text().splitlines()
        if line.strip()
    ]


def append_record(
    payload: dict, decision_id: str | None = None, path: Path | None = None
) -> AuditRecord:
    p = _path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    existing = read_records(p)
    prev_hash = existing[-1].hash if existing else GENESIS_HASH
    rec = AuditRecord(
        decision_id=decision_id or uuid.uuid4().hex,
        timestamp=datetime.now(UTC).isoformat(),
        prev_hash=prev_hash,
        payload=payload,
    )
    rec.hash = record_hash(rec.prev_hash, rec.decision_id, rec.timestamp, rec.payload)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(rec.model_dump_json() + "\n")
    return rec


def get_record(decision_id: str, path: Path | None = None) -> AuditRecord | None:
    for rec in read_records(path):
        if rec.decision_id == decision_id:
            return rec
    return None


def verify_chain(path: Path | None = None) -> tuple[bool, int, int | None]:
    """(ok, records_checked, index of the first record that fails)."""
    records = read_records(path)
    prev = GENESIS_HASH
    for i, rec in enumerate(records):
        expected = record_hash(prev, rec.decision_id, rec.timestamp, rec.payload)
        if rec.prev_hash != prev or rec.hash != expected:
            return False, len(records), i
        prev = rec.hash
    return True, len(records), None


def profile_hash(profile: Profile) -> str:
    return _sha256(canonical_json(profile.model_dump(mode="json")))


def make_payload(
    outcome: RecourseOutcome,
    *,
    mode: str,
    job: JobTemplate,
    manifest: Manifest,
    profile: Profile,
    candidate_id: str,
    cv_sha256: str,
    explanation_hash: str | None,
    versions: dict,
) -> dict:
    """The record content described in the ranking-mode brief, Part 4."""
    decision = outcome.decision
    payload: dict[str, Any] = {
        "mode": mode,
        "candidate_id": candidate_id,
        "job_id": job.job_id,
        "as_of": config.AS_OF,
        "versions": {
            "job_version": job.version,
            "manifest_version": manifest.version,
            "scorer_version": config.SCORER_VERSION,
            "solver_version": config.SOLVER_VERSION,
            **versions,
        },
        "profile_hash": profile_hash(profile),
        "raw_cv_hash": cv_sha256,
        "score": decision.score,
        "max_score": decision.max_score,
        "decision": {
            "passed": decision.passed,
            "knockouts_passed": decision.knockouts_passed,
            "knockouts": [k.model_dump(mode="json") for k in decision.knockouts],
        },
        "actions_shown": [r.model_dump(mode="json") for r in outcome.routes],
        "explanation_text_hash": explanation_hash,
        "protected_exclusion_assert_passed": bool(
            outcome.assertions.get("protected_excluded_scorer")
            and outcome.assertions.get("protected_excluded_solver")
        ),
        "immutable_blockers": [b.model_dump(mode="json") for b in outcome.immutable_blockers],
        "no_feasible_path": (
            outcome.no_feasible_path.model_dump(mode="json")
            if outcome.no_feasible_path
            else None
        ),
        "absent_priors_applied": sorted(
            c.path for c in outcome.contributions if c.prior_applied
        ),
    }
    if mode == "A":
        payload["tau"] = decision.threshold
        payload["margin_eps"] = decision.margin_eps
    else:
        payload["N"] = decision.slots_n
        payload["bar"] = decision.threshold
        payload["rank"] = decision.rank
        payload["pool_size"] = decision.pool_size
        payload["tie_convention"] = "pessimistic: equal scores rank ahead of the candidate"
        payload["aggregate_line"] = outcome.aggregate_line
    return payload
