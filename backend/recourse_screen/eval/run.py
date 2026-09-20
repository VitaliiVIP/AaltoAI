"""End-to-end evaluation: render the synthetic corpus, extract each CV, score the
parser against the ground truth, then run both recourse modes on the extracted
profiles and again on the truth profiles.

Running both is the point: the truth run isolates solver behaviour from parser
error, so a low actionability rate on the extracted profiles can be attributed to
the right stage.
"""
from __future__ import annotations

import json
import traceback
from pathlib import Path
from typing import Any

from .. import config
from ..schemas import Profile
from .parser_metrics import aggregate, compare_profiles
from .recourse_metrics import recourse_metrics

REPORT_JSON = "eval_report.json"
REPORT_MD = "eval_report.md"


def _fmt(v: Any, nd: int = 3) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def _corpus_stats(records: list[dict]) -> dict[str, Any]:
    arche: dict[str, int] = {}
    for r in records:
        a = r["meta"]["archetype"]
        arche[a] = arche.get(a, 0) + 1
    return {
        "n": len(records),
        "rendered": sum(1 for r in records if r["rendered"]),
        "archetypes": dict(sorted(arche.items(), key=lambda kv: -kv[1])),
        "under_report": sum(1 for r in records if r["meta"]["under_report"]),
        "year_only_dates": sum(1 for r in records if r["meta"]["year_only_dates"]),
        "overlap": sum(1 for r in records if r["meta"]["overlap"]),
        "omitted_skills_total": sum(len(r["meta"]["omitted_skills"]) for r in records),
    }


def run_eval(n: int = 30, seed: int = 0, force_render: bool = False,
             force_extract: bool = False, render_only: bool = False,
             out_dir: Path | str = config.SYNTH_DIR) -> dict[str, Any]:
    from ..synth.render import render_corpus

    out = Path(out_dir)
    records = render_corpus(n, seed, out_dir=out, force=force_render)
    report: dict[str, Any] = {
        "n": n, "seed": seed, "as_of": config.AS_OF, "model": config.MODEL_ID,
        "corpus": _corpus_stats(records),
    }
    if render_only:
        report["note"] = "render-only run: no extraction, no recourse metrics"
        _write(out, report)
        return report

    # ---- extraction ------------------------------------------------------- #
    try:
        from ..extract.extractor import extract_profile
    except Exception as exc:
        report["extraction_error"] = f"extractor unavailable: {exc!r}"
        _write(out, report)
        return report

    rows: list[dict[str, Any]] = []
    extracted: list[tuple[str, Profile]] = []
    truths: list[tuple[str, Profile]] = []
    failures: list[dict[str, str]] = []

    for rec in records:
        if not rec["rendered"]:
            failures.append({"source": rec["text_path"], "error": "not rendered"})
            continue
        cid = Path(rec["text_path"]).stem
        text = Path(rec["text_path"]).read_text()
        truth = Profile.model_validate_json(Path(rec["truth_path"]).read_text())
        meta = json.loads(Path(rec["meta_path"]).read_text())
        truths.append((cid, truth))
        try:
            prof = extract_profile(text, source_file=f"{cid}.txt", use_cache=not force_extract)
        except Exception as exc:
            failures.append({"source": cid, "error": repr(exc),
                             "trace": traceback.format_exc(limit=3)})
            continue
        extracted.append((cid, prof))
        rows.append(compare_profiles(prof, truth, meta))

    report["parser"] = {"per_cv": rows, "aggregate": aggregate(rows),
                        "failures": failures, "n_extracted": len(extracted)}

    # ---- recourse --------------------------------------------------------- #
    from ..loaders import load_job, manifest_for_job

    job = load_job("data_scientist")
    manifest = manifest_for_job(job)
    recourse: dict[str, Any] = {}
    for label, pool in (("extracted", extracted), ("truth", truths)):
        for mode in ("A", "B"):
            key = f"{label}_{mode}"
            if not pool:
                recourse[key] = {"error": "no profiles"}
                continue
            try:
                recourse[key] = recourse_metrics(pool, job, manifest, mode=mode)
            except Exception as exc:
                recourse[key] = {"error": repr(exc)}
    report["recourse"] = recourse

    _write(out, report)
    return report


# --------------------------------------------------------------------------- #
# report writing
# --------------------------------------------------------------------------- #

def _write(out: Path, report: dict[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / REPORT_JSON).write_text(json.dumps(report, indent=1, default=str))
    (out / REPORT_MD).write_text(render_markdown(report))


def render_markdown(report: dict[str, Any]) -> str:
    L: list[str] = []
    c = report["corpus"]
    L.append("# Synthetic evaluation report")
    L.append("")
    L.append(f"`n={report['n']}` seed `{report['seed']}` as-of `{report['as_of']}` "
             f"renderer/extractor `{report['model']}`")
    L.append("")
    L.append("## Corpus")
    L.append("")
    L.append("| property | value |")
    L.append("|---|---|")
    L.append(f"| profiles sampled | {c['n']} |")
    L.append(f"| CVs rendered | {c['rendered']} |")
    L.append(f"| under-reporting variants | {c['under_report']} |")
    L.append(f"| skills deliberately omitted | {c['omitted_skills_total']} |")
    L.append(f"| year-only date variants | {c['year_only_dates']} |")
    L.append(f"| overlapping-contract variants | {c['overlap']} |")
    L.append("")
    L.append("| archetype | count |")
    L.append("|---|---|")
    for a, k in c["archetypes"].items():
        L.append(f"| {a} | {k} |")
    L.append("")

    if "extraction_error" in report:
        L.append(f"> Extraction stage skipped: {report['extraction_error']}")
        L.append("")
    if report.get("note"):
        L.append(f"> {report['note']}")
        L.append("")

    p = report.get("parser", {}).get("aggregate")
    if p and p.get("n"):
        s = p["skills"]
        L.append("## Parser accuracy")
        L.append("")
        L.append("**Headline.** Recall splits hard by whether the skill was written in the CV at "
                 "all. Skills the renderer deliberately omitted are unrecoverable by any parser; "
                 "that gap is what the restatement channel exists for, not a tuning target.")
        L.append("")
        L.append("| skill recall | n | recall |")
        L.append("|---|---|---|")
        L.append(f"| **stated in the CV text** | {s['n_stated']} | **{_fmt(s['recall_stated'])}** |")
        L.append(f"| **deliberately omitted** | {s['n_omitted']} | **{_fmt(s['recall_omitted'])}** |")
        L.append("")
        L.append("| metric | value | demo target |")
        L.append("|---|---|---|")
        L.append(f"| skills micro-F1 | {_fmt(s['micro_f1'])} | >= 0.85 |")
        L.append(f"| skills micro-precision | {_fmt(s['micro_precision'])} | |")
        L.append(f"| skills micro-recall (all) | {_fmt(s['micro_recall'])} | |")
        L.append(f"| skills macro-F1 | {_fmt(s['macro_f1'])} | |")
        L.append(f"| per-skill months MAE | {_fmt(p['skill_months']['mae'], 2)} | <= 6 months |")
        L.append(f"| experience months MAE | {_fmt(p['experience_months']['mae'], 2)} | <= 6 months |")
        for f, v in p["experience_months"]["per_field"].items():
            L.append(f"| &nbsp;&nbsp;{f} MAE | {_fmt(v['mae'], 2)} | |")
        L.append(f"| education level exact match | {_fmt(p['education_level_exact'])} | >= 0.95 |")
        L.append(f"| seniority exact match | {_fmt(p['seniority_exact'])} | |")
        L.append(f"| role count exact | {_fmt(p['role_count_exact'])} | |")
        L.append(f"| evidence verification rate | {_fmt(p['evidence_verification_rate'])} "
                 f"(n={p['evidence_n']}) | |")
        L.append(f"| hallucination rate | {_fmt(p['hallucination_rate'])} | <= 0.02 |")
        L.append("")
        sub = p["subsets"]
        L.append("| subset | n | note |")
        L.append("|---|---|---|")
        L.append(f"| under-reporting CVs | {sub['under_report']['n'] } | "
                 f"stated recall {_fmt(sub['under_report']['recall_stated'])}, "
                 f"omitted recall {_fmt(sub['under_report']['recall_omitted'])} |")
        L.append(f"| year-only dates | {sub['year_only_dates']['n']} | "
                 f"experience MAE {_fmt(sub['year_only_dates']['experience_mae'], 2)} |")
        L.append(f"| month-precision dates | {sub['month_dates']['n']} | "
                 f"experience MAE {_fmt(sub['month_dates']['experience_mae'], 2)} |")
        L.append("")

    r = report.get("recourse")
    if r:
        L.append("## Recourse")
        L.append("")
        L.append("`extracted` runs on parsed profiles; `truth` runs on the ground-truth profiles "
                 "and isolates solver behaviour from parser error.")
        L.append("")
        L.append("| run | pass rate | rejected | validity | actionability | L0 mean | L0 max | "
                 "cost median | diversity | immutable | no path |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for key in ("extracted_A", "extracted_B", "truth_A", "truth_B"):
            m = r.get(key)
            if not m:
                continue
            if "error" in m:
                L.append(f"| {key} | error: {m['error'][:60]} | | | | | | | | | |")
                continue
            L.append("| {k} | {pr} | {nr} | {v} | {a} | {lm} | {lx} | {cm} | {d} | {ib} | {nf} |".format(
                k=key, pr=_fmt(m["pass_rate"]), nr=m["n_rejected"], v=_fmt(m["validity"]),
                a=_fmt(m["actionability_rate"]), lm=_fmt(m["l0_mean"], 2), lx=_fmt(m["l0_max"]),
                cm=_fmt(m["cost_median"], 1), d=_fmt(m["diversity_mean_distinct_supports"], 2),
                ib=_fmt(m["immutable_blocker_rate"]), nf=_fmt(m["no_feasible_path_rate"])))
        L.append("")

    rows = report.get("parser", {}).get("per_cv") or []
    if rows:
        L.append("## Per-CV")
        L.append("")
        L.append("| cv | archetype | under-report | year-only | skills P | skills R | "
                 "R stated | R omitted | months MAE | exp MAE | roles |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for row in rows:
            sk = row["skills"]
            L.append("| {f} | {a} | {u} | {y} | {p} | {r} | {rs} | {ro} | {mm} | {em} | {rr} |".format(
                f=row["source_file"], a=row["archetype"], u=_fmt(row["under_report"]),
                y=_fmt(row["year_only_dates"]), p=_fmt(sk["precision"], 2), r=_fmt(sk["recall"], 2),
                rs=_fmt(sk["stated"]["recall"], 2),
                ro=(_fmt(sk["omitted"]["recall"], 2) if sk["omitted"]["n"] else "-"),
                mm=_fmt(row["skill_months"]["mae"], 1), em=_fmt(row["experience_months"]["mae"], 1),
                rr=f"{row['roles']['extracted']}/{row['roles']['truth']}"))
        L.append("")

    fails = report.get("parser", {}).get("failures") or []
    if fails:
        L.append("## Failures")
        L.append("")
        for f in fails:
            L.append(f"- `{f.get('source')}`: {f.get('error')}")
        L.append("")
    return "\n".join(L) + "\n"
