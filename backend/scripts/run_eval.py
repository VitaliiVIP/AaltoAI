#!/usr/bin/env python3
"""CLI for the synthetic evaluation harness.

    uv run python scripts/run_eval.py --n 30 --seed 0
    uv run python scripts/run_eval.py --n 30 --seed 0 --render-only
    uv run python scripts/run_eval.py --n 30 --force-render --force-extract
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from recourse_screen import config  # noqa: E402
from recourse_screen.eval.run import REPORT_JSON, REPORT_MD, run_eval  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Render the synthetic corpus and evaluate the pipeline.")
    ap.add_argument("--n", type=int, default=30, help="number of synthetic CVs")
    ap.add_argument("--seed", type=int, default=0, help="sampler seed")
    ap.add_argument("--render-only", action="store_true", help="stop after rendering the corpus")
    ap.add_argument("--force-render", action="store_true", help="re-render CVs that already exist")
    ap.add_argument("--force-extract", action="store_true", help="bypass the profile cache")
    ap.add_argument("--out-dir", default=str(config.SYNTH_DIR))
    args = ap.parse_args()

    report = run_eval(n=args.n, seed=args.seed, force_render=args.force_render,
                      force_extract=args.force_extract, render_only=args.render_only,
                      out_dir=args.out_dir)

    c = report["corpus"]
    print(f"corpus: {c['rendered']}/{c['n']} rendered | under-report {c['under_report']} | "
          f"year-only {c['year_only_dates']} | overlap {c['overlap']}")
    print("archetypes: " + ", ".join(f"{k}={v}" for k, v in c["archetypes"].items()))
    agg = report.get("parser", {}).get("aggregate") or {}
    if agg.get("n"):
        s = agg["skills"]
        print(f"parser: micro-F1 {s['micro_f1']:.3f} | recall stated {s['recall_stated']:.3f} "
              f"| recall omitted {s['recall_omitted']:.3f} | "
              f"hallucination {agg['hallucination_rate']:.3f}")
    for key, m in (report.get("recourse") or {}).items():
        if "error" in m:
            print(f"recourse {key}: {m['error'][:100]}")
        else:
            print(f"recourse {key}: pass {m['pass_rate']:.2f} | validity {m['validity']:.2f} | "
                  f"actionable {m['actionability_rate']:.2f}")
    out = Path(args.out_dir)
    print(f"wrote {out / REPORT_JSON} and {out / REPORT_MD}")
    if report.get("extraction_error"):
        print(json.dumps({"extraction_error": report["extraction_error"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
