import { useEffect, useState } from "react";
import type { JobSummary, PoolRow, ScreenResult } from "../apiTypes";
import { tierOf } from "../types";
import { deriveName } from "../candidateMeta";
import { auditUrl } from "../api";
import {
  creditedWithoutEvidence,
  fmtValue,
  gapPills,
  matchedPills,
  nfpReason,
  partialProgressView,
  recruiterSummary,
  routeViews,
  shortId,
  yearsOf,
} from "../present";
import type { RouteView } from "../present";
import type { Phase } from "../useScreening";
import CvModal from "./CvModal";
import ParsedCvModal from "./ParsedCvModal";
import ScoreChip from "./ScoreChip";

interface ExplainPanelProps {
  result: ScreenResult | null;
  row: PoolRow | null;
  job: JobSummary | null;
  maxScore: number;
  phase: Phase;
  error: string | null;
  onDeleteCv: (id: string) => void;
}

function RouteBody({ route }: { route: RouteView }) {
  return (
    <div className="route-body">
      {route.deltas.map((d) => (
        <div className={"delta" + (d.unstated ? " absent" : "")} key={d.deltaId}>
          <p className="delta-sentence">
            {d.unstated && <span className="delta-glyph">?</span>}
            {d.sentence}
          </p>
          <p className="delta-meta">
            {d.unstated
              ? "Not on the CV — a question, not an instruction."
              : `${d.from} → ${d.to}`}
            {d.points != null && <> · {d.points > 0 ? `+${d.points}` : d.points} pts</>}
            {d.typicalTimeMonths != null && <> · typically {d.typicalTimeMonths} mo</>}
            {" · "}
            {d.actionability.replace(/_/g, " ")}
          </p>
        </div>
      ))}
    </div>
  );
}

export default function ExplainPanel({
  result,
  row,
  job,
  maxScore,
  phase,
  error,
  onDeleteCv,
}: ExplainPanelProps) {
  const [cvOpen, setCvOpen] = useState(false);
  const [parseOpen, setParseOpen] = useState(false);
  const [activeRoute, setActiveRoute] = useState(0);

  const candidateId = result?.candidate_id ?? row?.candidate_id ?? null;

  // Close the CV modal and reset the route selection whenever the selection
  // changes underneath them.
  useEffect(() => {
    setCvOpen(false);
    setParseOpen(false);
    setActiveRoute(0);
  }, [candidateId]);

  if (!candidateId) {
    return (
      <section className="col col-explain" aria-label="Match explanation">
        <div className="col-header">
          <h2>Why this match?</h2>
        </div>
        <div className="explain-body">
          <p className="empty-note">Select a candidate.</p>
        </div>
      </section>
    );
  }

  const name = deriveName(candidateId);
  const busy = phase === "loading" || phase === "explaining";

  // The previous result stays on screen while a new one loads, so scrubbing the
  // score scale never blanks the column.
  const d = result?.decision ?? null;
  const matched = result ? matchedPills(result, job) : [];
  const prior = result ? creditedWithoutEvidence(result) : [];
  const gaps = result ? gapPills(result, job) : [];
  const routes = result ? routeViews(result, job) : [];
  const partial = result ? partialProgressView(result, job) : null;
  const blockers = result?.immutable_blockers ?? [];
  const nfp = result?.no_feasible_path ?? null;
  const shown = routes[Math.min(activeRoute, Math.max(routes.length - 1, 0))] ?? null;

  const tier = d
    ? tierOf({ knockouts_passed: d.knockouts_passed, passed: d.passed })
    : row
      ? tierOf({ knockouts_passed: row.knockouts_passed, passed: row.decision === "advance" })
      : "yellow";

  return (
    <section className="col col-explain" aria-label="Match explanation">
      <div className="col-header">
        <h2>Why this match?</h2>
        <button className="open-cv-btn secondary" onClick={() => setParseOpen(true)}>
          What we read
        </button>
        <button className="open-cv-btn" onClick={() => setCvOpen(true)}>
          Open CV
        </button>
        <button
          className="open-cv-btn danger"
          onClick={() => onDeleteCv(candidateId)}
          aria-label="Delete CV"
          title="Delete CV"
        >
          ×
        </button>
      </div>

      <div className={"explain-body" + (busy ? " stale" : "")}>
        {busy && <div className="loading-bar" role="status" aria-label="Screening" />}

        {phase === "error" && <div className="panel-error">{error}</div>}

        <div className="explain-name">{name}</div>
        <p className="name-note">
          Reconstructed from the filename. The screening model never sees it — protected
          attributes are not representable in the profile at all.
        </p>

        <div className="explain-score-row">
          <ScoreChip score={d?.score ?? row?.score ?? 0} max={maxScore} tier={tier} />
          {d && (
            <span className={"decision-badge " + (d.passed ? "pass" : "fail")}>
              {d.passed ? "ADVANCES" : "NOT ADVANCED"}
            </span>
          )}
          {result && <span className="cv-sub">{yearsOf(result)} yrs experience</span>}
        </div>

        {d && d.mode === "B" && d.rank != null && (
          <p className="rank-strip">
            Rank <strong>{d.rank}</strong> of {d.pool_size} · top {d.slots_n} advance
          </p>
        )}

        {result && <p className="explain-summary">{recruiterSummary(result, job)}</p>}

        {d && (
          <div className="explain-block">
            <h3>Hard requirements</h3>
            <p className="block-note">
              Evaluated before any weighted score, and never traded off against it.
            </p>
            <div className="pill-list ko-row">
              {d.knockouts.map((k) => (
                <span className={"pill " + (k.passed ? "match" : "ko-fail")} key={k.rule}>
                  {k.passed ? "✓" : "✗"} {k.rule}
                  {!k.passed && <> — currently {fmtValue(k.current_value)}</>}
                </span>
              ))}
            </div>
          </div>
        )}

        <div className="explain-block">
          <h3>Matched requirements</h3>
          {matched.length ? (
            <div className="pill-list">
              {matched.map((m) => (
                <span className="pill match" key={m.path} title={`${m.detail} · ${m.points} pts`}>
                  {m.phrase}
                </span>
              ))}
            </div>
          ) : (
            <p className="empty-note">No requirements matched.</p>
          )}
          {prior.length > 0 && (
            <p className="block-note">
              Credited without evidence (the CV did not say, and the job template grants a
              prior): {prior.map((p) => p.phrase).join(", ")}.
            </p>
          )}
        </div>

        <div className="explain-block">
          <h3>Gaps identified</h3>
          {gaps.length ? (
            <div className="pill-list">
              {gaps.map((g) => (
                <span
                  className={"pill " + (g.unstated ? "unstated" : "gap")}
                  key={g.path}
                  title={
                    g.unstated
                      ? "Not mentioned on the CV — a question, not an instruction"
                      : `Below the bar (currently ${g.detail})`
                  }
                >
                  {g.unstated && "? "}
                  {g.phrase} <span className="gap-points">−{g.points}</span>
                </span>
              ))}
            </div>
          ) : (
            <p className="empty-note">No gaps — full match.</p>
          )}
          {gaps.some((g) => g.unstated) && (
            <p className="block-note">
              Amber items were never mentioned on the CV. Missing is not the same as absent —
              those are questions for the candidate, not instructions.
            </p>
          )}
        </div>

        {blockers.length > 0 && (
          <div className="explain-block">
            <h3>Fixed requirement — no action would change this</h3>
            {blockers.map((b) => (
              <div className="blocker-box" key={b.rule}>
                <p>{b.disclosure}</p>
                <p className="delta-meta">
                  {b.rule} · currently {fmtValue(b.current_value)}
                </p>
              </div>
            ))}
          </div>
        )}

        {nfp && (
          <div className="explain-block">
            <h3>No feasible path</h3>
            <div className="nfp-box">
              <p>
                No combination of changes clears the bar within the
                {job ? ` ${job.horizon_months}-month ` : " "}horizon. {nfpReason(nfp.reason)}{" "}
                Gap remaining: <strong>{nfp.gap_remaining}</strong>. Human review route applies.
              </p>
            </div>
            {partial && (
              <>
                <p className="block-note">
                  Nearest partial progress — this would <strong>not</strong> have flipped the
                  decision (reaches {partial.newScore}/{maxScore}).
                </p>
                <RouteBody route={partial} />
              </>
            )}
          </div>
        )}

        {routes.length > 0 && (
          <div className="explain-block">
            <h3>Algorithmic recourse — what would change the outcome</h3>
            <p className="block-note">
              Any one of these routes flips the decision on its own. Each is solved for minimum
              effort and re-tested against the scorer.
            </p>
            <div className="route-chips" role="tablist">
              {routes.map((r, i) => (
                <button
                  key={r.routeId}
                  role="tab"
                  aria-selected={i === activeRoute}
                  className={"route-chip" + (i === activeRoute ? " active" : "")}
                  onClick={() => setActiveRoute(i)}
                >
                  <strong>{r.label}</strong>
                  <span>
                    +{r.gain} pts · ~{r.months} mo
                  </span>
                </button>
              ))}
            </div>
            {shown && (
              <>
                <p className="route-meta">
                  → {shown.newScore}/{maxScore} · effort {shown.cost} · ≈{shown.months} months
                  {shown.rank != null && <> · would place ~rank {shown.rank}</>} ·{" "}
                  {shown.flipTested ? "flip-tested ✓" : "flip test ✗"}
                </p>
                <RouteBody route={shown} />
              </>
            )}
          </div>
        )}

        {d?.passed && routes.length === 0 && blockers.length === 0 && !nfp && (
          <p className="empty-note">No recourse needed — this candidate already clears the bar.</p>
        )}

        <p className="reg-note">
          Decision made with human oversight per GDPR Art. 22 and EU AI Act Art. 14 (high-risk
          employment system, Annex III pt. 4). Explanation generated per EU AI Act Art. 86 (right
          to explanation of individual decision-making).
        </p>

        {result && (
          <p className="audit-line">
            decision{" "}
            <a href={auditUrl(result.decision_id)} target="_blank" rel="noreferrer">
              {shortId(result.decision_id)}…
            </a>{" "}
            · screened {result.as_of} · {result.versions.scorer}/{result.versions.solver}
          </p>
        )}
      </div>

      {cvOpen && (
        <CvModal
          candidateId={candidateId}
          hasPdf={row?.has_pdf ?? false}
          onClose={() => setCvOpen(false)}
        />
      )}

      <ParsedCvModal
        open={parseOpen}
        candidateId={candidateId}
        jobId={job?.job_id ?? "backend_engineer"}
        onClose={() => setParseOpen(false)}
      />
    </section>
  );
}
