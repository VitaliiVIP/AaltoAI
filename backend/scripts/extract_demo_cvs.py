#!/usr/bin/env python
"""Extract every demo CV and print a one-line-per-CV summary.

    uv run python scripts/extract_demo_cvs.py [--force] [--only NAME]

Without --force the raw model output is reused from data/profiles_raw/, so re-running
after a post-processing change is free. --force pays for a fresh extraction (~$0.10/CV).
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from recourse_screen import config  # noqa: E402
from recourse_screen.extract.extractor import ExtractionError, extract_profile  # noqa: E402
from recourse_screen.extract.pdf import load_cv_text  # noqa: E402
from recourse_screen.extract.postprocess import pii_warnings, verification_stats  # noqa: E402
from recourse_screen.loaders import load_manifest  # noqa: E402
from recourse_screen.schemas import Profile  # noqa: E402

# (taxonomy id, one-letter flag) for the skills the data science job weighs.
FLAG_SKILLS = [
    ("scikit_learn", "S"), ("pytorch", "P"), ("tensorflow", "T"),
    ("statistics", "X"), ("sql", "Q"), ("spark", "K"),
]
FLAG_DERIVED = [
    ("ml_framework_held", "m"), ("cloud_platform_held", "c"),
    ("data_pipeline_held", "p"), ("sql_held", "s"), ("visualisation_held", "v"),
]

HEADER = (f"{'candidate':<24} {'tot':>4} {'sw':>4} {'data':>5} {'py':>4} "
          f"{'SPTXQK':<7} {'mcpsv':<6} {'education':<12} {'evidence':>9}  unmatched")


def _flag(entry_held) -> bool | None:
    if entry_held is None:
        return None
    if entry_held.derivation == "denied":
        return False
    return True if entry_held.value is True else None


def skill_flags(profile: Profile) -> str:
    out = []
    for skill_id, letter in FLAG_SKILLS:
        entry = profile.skills.get(skill_id)
        state = _flag(entry.held) if entry else None
        out.append(letter if state is True else ("!" if state is False else "."))
    return "".join(out)


def derived_flags(profile: Profile) -> str:
    out = []
    for name, letter in FLAG_DERIVED:
        env = profile.derived.get(name)
        if env is None or env.value is None:
            out.append(".")
        elif env.value is True:
            out.append(letter)
        else:
            out.append("!")
    return "".join(out)


def _months(env) -> str:
    return "-" if env.value is None else str(env.value)


def summary_line(candidate_id: str, profile: Profile, stats: dict) -> str:
    python = profile.skills.get("python")
    py_months = "-"
    if python is not None:
        if python.held.derivation == "denied":
            py_months = "no"
        elif python.months.value is not None:
            py_months = str(python.months.value)
        elif python.held.value is True:
            py_months = "held"
    education = profile.education.highest_level.value or "-"
    if profile.education.in_progress.value is True:
        education = f"{education}*"
    evidence = f"{stats['verified']}/{stats['total']}"
    unmatched = ", ".join(profile.unmatched_skills) or "-"
    return (f"{candidate_id:<24} "
            f"{_months(profile.experience.total_months):>4} "
            f"{_months(profile.experience.software_months):>4} "
            f"{_months(profile.experience.data_months):>5} "
            f"{py_months:>4} "
            f"{skill_flags(profile):<7} {derived_flags(profile):<6} "
            f"{education:<12} {evidence:>9}  {unmatched}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true",
                        help="ignore the raw cache and call the API again")
    parser.add_argument("--only", metavar="NAME",
                        help="only CVs whose filename contains NAME")
    parser.add_argument("--verbose", "-v", action="store_true", help="debug logging")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")

    paths = sorted(p for p in config.CV_TEXT_DIR.iterdir()
                   if p.suffix.lower() in (".txt", ".pdf"))
    if args.only:
        paths = [p for p in paths if args.only.lower() in p.name.lower()]
    if not paths:
        print(f"no CVs matched under {config.CV_TEXT_DIR}", file=sys.stderr)
        return 1

    manifest = load_manifest("data_science.json")
    print(f"as_of {config.AS_OF} | model {config.MODEL_ID} | "
          f"{len(paths)} CV(s) | cache {'off' if args.force else 'on'}\n")
    print(HEADER)
    print("-" * len(HEADER))

    total_quotes = verified_quotes = 0
    failures: list[str] = []
    warnings: list[str] = []
    errors: list[str] = []

    for path in paths:
        candidate_id = path.stem
        try:
            cv_text = load_cv_text(path)
            profile = extract_profile(cv_text, source_file=path.name,
                                      use_cache=not args.force, manifest=manifest)
        except (ExtractionError, OSError) as exc:
            errors.append(f"{candidate_id}: {exc}")
            print(f"{candidate_id:<24} EXTRACTION FAILED: {exc}")
            continue

        stats = verification_stats(profile)
        total_quotes += stats["total"]
        verified_quotes += stats["verified"]
        failures += [f"{candidate_id} -> {f}" for f in stats["failures"]]
        warnings += [f"{candidate_id} -> {w}" for w in pii_warnings(profile)]
        print(summary_line(candidate_id, profile, stats))

    rate = (verified_quotes / total_quotes) if total_quotes else 1.0
    print()
    print(f"evidence verified: {verified_quotes}/{total_quotes} ({rate:.1%}) "
          f"across {len(paths) - len(errors)} profile(s)")
    print("flags: SPTXQK = scikit-learn pytorch tensorflow statistics sql spark; "
          "mcpsv = derived ml-framework cloud pipeline sql visualisation")
    print("       letter = held, '!' = denied by the CV, '.' = absent (unverified, not zero)")
    print("months are calendar months; '*' on education = in progress")
    print(f"profiles written to {config.PROFILE_CACHE_DIR}")

    if failures:
        print(f"\nunverified quotes ({len(failures)}):")
        for f in failures:
            print(f"  {f}")
    if warnings:
        print(f"\ncontact details inside quotes ({len(warnings)}):")
        for w in warnings:
            print(f"  {w}")
    if errors:
        print(f"\nfailed CVs ({len(errors)}):")
        for e in errors:
            print(f"  {e}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
