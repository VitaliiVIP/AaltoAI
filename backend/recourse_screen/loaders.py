"""Load taxonomy, manifests, job templates and cached profiles from disk."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import yaml

from . import config
from .schemas import JobTemplate, Manifest, Profile


class Taxonomy:
    def __init__(self, data: dict):
        self.version: str = data["version"]
        self.concepts: list[dict] = data["concepts"]
        self.ids: list[str] = [c["id"] for c in self.concepts]
        self.by_id: dict[str, dict] = {c["id"]: c for c in self.concepts}
        # alias (lowercased) -> id; includes label and id themselves
        self.alias_map: dict[str, str] = {}
        for c in self.concepts:
            for a in [c["id"], c["label"], *c.get("aliases", [])]:
                self.alias_map.setdefault(a.lower().strip(), c["id"])

    def canonicalise(self, raw: str) -> str | None:
        key = raw.lower().strip()
        if key in self.alias_map:
            return self.alias_map[key]
        key2 = key.replace("-", " ").replace("_", " ")
        for alias, cid in self.alias_map.items():
            if alias.replace("-", " ").replace("_", " ") == key2:
                return cid
        return None

    def label(self, cid: str) -> str:
        return self.by_id.get(cid, {}).get("label", cid)


@lru_cache(maxsize=None)
def load_taxonomy(path: Path | None = None) -> Taxonomy:
    p = path or config.TAXONOMY_PATH
    return Taxonomy(json.loads(Path(p).read_text()))


@lru_cache(maxsize=None)
def load_manifest(name_or_path: str | Path) -> Manifest:
    p = Path(name_or_path)
    if not p.is_absolute() and not p.exists():
        p = config.MANIFEST_DIR / p
    return Manifest.model_validate(json.loads(p.read_text()))


def _job_path(name: str) -> Path:
    """An edited job in JOBS_DIR shadows the seed of the same id; otherwise the
    shipped default answers. Returns the JOBS_DIR path when neither exists so the
    caller still gets a FileNotFoundError naming the writable location."""
    for d in (config.JOBS_DIR, config.JOB_SEED_DIR):
        if (d / name).exists():
            return d / name
    return config.JOBS_DIR / name


@lru_cache(maxsize=None)
def load_job(job_id_or_path: str | Path) -> JobTemplate:
    p = Path(job_id_or_path)
    if p.suffix not in (".yaml", ".yml"):
        p = _job_path(f"{job_id_or_path}.yaml")
    if not p.is_absolute() and not p.exists():
        p = _job_path(str(p))
    job = JobTemplate.model_validate(yaml.safe_load(p.read_text()))
    # Resolve a relative manifest name next to the job file first (fixtures), then MANIFEST_DIR.
    mp = Path(job.manifest)
    if (
        not mp.is_absolute()
        and (p.parent / mp).exists()
        and p.parent not in (config.JOBS_DIR, config.JOB_SEED_DIR)
    ):
        job.manifest = str((p.parent / mp).resolve())
    # A point-authored job has no per-step weights until the manifest supplies the
    # caps, so binding is part of loading rather than something callers can forget.
    return job.bind(manifest_for_job(job))


def manifest_for_job(job: JobTemplate, manifest_dir: Path | None = None) -> Manifest:
    p = Path(job.manifest)
    if not p.is_absolute():
        p = (manifest_dir or config.MANIFEST_DIR) / p
    return load_manifest(p)


def list_jobs() -> list[str]:
    seed = {p.stem for p in config.JOB_SEED_DIR.glob("*.yaml")}
    edited = {p.stem for p in config.JOBS_DIR.glob("*.yaml")}
    return sorted(seed | edited)


def load_profile(path: Path) -> Profile:
    return Profile.model_validate(json.loads(Path(path).read_text()))


def save_profile(profile: Profile, path: Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(profile.model_dump_json(indent=1))


def load_cv_text(candidate_id: str) -> str:
    """The exact text every evidence offset in this candidate's profile indexes.

    Resolved through the cached-profile map rather than by joining the id onto a
    path, so a candidate_id arriving from a URL cannot walk out of CV_TEXT_DIR.
    """
    if candidate_id not in list_cached_profiles():
        raise KeyError(f"unknown candidate_id {candidate_id!r}")
    return (config.CV_TEXT_DIR / f"{candidate_id}.txt").read_text()


def list_cached_profiles(*, demo_only: bool = True) -> dict[str, Path]:
    """candidate_id -> profile path. candidate_id is the source file stem.
    With demo_only, only profiles whose source text lives in CV_TEXT_DIR are
    returned, so synthetic/eval extractions never leak into the demo pool."""
    demo_stems = {p.stem for p in config.CV_TEXT_DIR.glob("*.txt")}
    out: dict[str, Path] = {}
    for p in sorted(config.PROFILE_CACHE_DIR.glob("*.json")):
        try:
            data = json.loads(p.read_text())
            src = data.get("provenance", {}).get("source_file")
        except Exception:
            src = None
        cid = Path(src).stem if src else p.stem
        if demo_only and cid not in demo_stems:
            continue
        out[cid] = p
    return out
