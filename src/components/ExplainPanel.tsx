import type { Candidate } from "../types";
import ScoreChip from "./ScoreChip";

interface ExplainPanelProps {
  candidate: Candidate;
}

export default function ExplainPanel({ candidate }: ExplainPanelProps) {
  return (
    <section className="col col-explain" aria-label="Match explanation">
      <div className="col-header">
        <h2>Why this match?</h2>
      </div>

      <div className="explain-body">
        <div className="explain-name">{candidate.name}</div>
        <div className="explain-score-row">
          <ScoreChip score={candidate.score} />
          <span className="cv-sub">{candidate.years} yrs experience</span>
        </div>
        <p className="explain-summary">{candidate.summary}</p>

        <div className="explain-block">
          <h3>Matched requirements</h3>
          {candidate.matched.length ? (
            <div className="pill-list">
              {candidate.matched.map((m) => (
                <span className="pill match" key={m}>
                  {m}
                </span>
              ))}
            </div>
          ) : (
            <p className="empty-note">No requirements matched.</p>
          )}
        </div>

        <div className="explain-block">
          <h3>Gaps identified</h3>
          {candidate.missing.length ? (
            <div className="pill-list">
              {candidate.missing.map((m) => (
                <span className="pill gap" key={m}>
                  {m}
                </span>
              ))}
            </div>
          ) : (
            <p className="empty-note">No gaps — full match.</p>
          )}
        </div>

        <div className="explain-block">
          <h3>Algorithmic recourse — what would change the outcome</h3>
          {candidate.recourse.length ? (
            <div className="recourse-list">
              {candidate.recourse.map((r) => (
                <div className="recourse-item" key={r.change}>
                  <span className="recourse-text">{r.change}</span>
                  <span className="recourse-impact">{r.impact}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="empty-note">No recourse needed — candidate already clears the bar.</p>
          )}
        </div>

        <p className="reg-note">
          Decision made with human oversight per GDPR Art. 22 and EU AI Act Art. 14 (high-risk employment
          system, Annex III pt. 4). Explanation generated per EU AI Act Art. 86 (right to explanation of
          individual decision-making).
        </p>
      </div>
    </section>
  );
}
