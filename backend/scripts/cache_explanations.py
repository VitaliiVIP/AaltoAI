#!/usr/bin/env python
"""Write the model's sentences for every demo decision into data/explanations/.

    uv run python scripts/cache_explanations.py [--dry-run] [--job ID] [--pool REGEX] [--only NAME]

The public API never calls the model. This script is the one place that does:
it screens every pooled candidate in mode A and in mode B for every N the UI
can reach (1 .. pool size), and for each rejection whose prompt is not yet in
the cache it calls the verbaliser once and stores the checked sentences. Re-
running is free for everything already cached. --dry-run only counts.

The cache is keyed by the exact prompt, so it is specific to the job as
currently configured *and*, in mode B, to the pool: rank and target both depend
on who else is in it. Cache against the pool the deployment will have -- the
shipped demo set is `--pool '^cv[0-9]+_'`, which also keeps any CV dropped in
locally for a one-off out of it. Editing the job in the UI (or a redeploy that
changes the job version) means the affected decisions fall back to the templates
until this is run again.
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from recourse_screen import config, pipeline  # noqa: E402
from recourse_screen.loaders import load_job  # noqa: E402
from recourse_screen.schemas import Explanation, Profile  # noqa: E402


def _needs_model(explanation: Explanation | None) -> bool:
    """True when the decision has deltas and the cache has no sentences for them."""
    return explanation is not None and explanation.fallback_used


def _screen(cid: str, profile: Profile, pool, *, job: str, mode: str, N: int | None,
            live: bool) -> Explanation | None:
    result = pipeline.screen_profile(
        profile, candidate_id=cid, job_id=job, mode=mode, N=N,
        explain=True, allow_live_llm=live, pool=pool, write_audit=False,
    )
    return result.explanation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be generated; call nothing")
    parser.add_argument("--job", default="data_scientist", help="job id (default: data_scientist)")
    parser.add_argument("--pool", metavar="REGEX",
                        help="restrict the mode-B pool to candidate ids matching REGEX "
                             "(the shipped demo set is '^cv[0-9]+_')")
    parser.add_argument("--only", metavar="NAME", help="only candidates whose id contains NAME")
    parser.add_argument("--verbose", "-v", action="store_true", help="debug logging")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")

    pool = pipeline.load_pool()
    if args.pool:
        pool = [(cid, p) for cid, p in pool if re.search(args.pool, cid)]
    if not pool:
        print(f"no cached profiles under {config.PROFILE_CACHE_DIR}"
              + (f" match {args.pool!r}" if args.pool else ""), file=sys.stderr)
        return 1
    targets = [(cid, p) for cid, p in pool if not args.only or args.only.lower() in cid.lower()]
    if not targets:
        print(f"no candidate id contains {args.only!r}", file=sys.stderr)
        return 1

    job = load_job(args.job)
    settings: list[tuple[str, int | None]] = [("A", None)] + [("B", n) for n in range(1, len(pool) + 1)]
    print(f"job {job.job_id} {job.version} | model {config.MODEL_ID} | pool {len(pool)} | "
          f"{len(targets)} candidate(s) x {len(settings)} setting(s) | "
          f"cache {config.EXPLANATION_CACHE_DIR}\n")

    passed = no_deltas = cached = generated = failed = 0
    for cid, profile in targets:
        line: list[str] = []
        for mode, n in settings:
            label = mode if n is None else f"B{n}"
            explanation = _screen(cid, profile, pool, job=args.job, mode=mode, N=n, live=False)
            if explanation is None:
                passed += 1
                line.append(f"{label}:pass")
                continue
            if not explanation.sentences:
                no_deltas += 1
                line.append(f"{label}:none")
                continue
            if not _needs_model(explanation):
                cached += 1
                line.append(f"{label}:ok")
                continue
            if args.dry_run:
                generated += 1
                line.append(f"{label}:MISS")
                continue
            explanation = _screen(cid, profile, pool, job=args.job, mode=mode, N=n, live=True)
            if _needs_model(explanation):
                failed += 1
                line.append(f"{label}:FAIL({','.join(explanation.check_failures) or '?'})")
            else:
                generated += 1
                line.append(f"{label}:new")
        print(f"{cid:<24} {' '.join(line)}")

    print()
    verb = "would generate" if args.dry_run else "generated"
    print(f"cached {cached} | {verb} {generated} | failed {failed} | "
          f"passed (no explanation) {passed} | no deltas {no_deltas}")
    print("MISS = prompt not in cache; ok = served from cache; new = written this run")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
