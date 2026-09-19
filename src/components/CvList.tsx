import type { Candidate, EmailStatus } from "../types";
import ScoreChip from "./ScoreChip";

interface CvListProps {
  candidates: Candidate[];
  selectedId: string;
  emailStatus: Record<string, EmailStatus>;
  onSelect: (id: string) => void;
}

export default function CvList({ candidates, selectedId, emailStatus, onSelect }: CvListProps) {
  const selected = candidates.find((c) => c.id === selectedId) ?? candidates[0];
  const markerTop = 100 - selected.score; // green(top)=100 score, red(bottom)=0 score

  return (
    <section className="col col-cvs" aria-label="Uploaded CVs">
      <div className="col-header">
        <h2>Uploaded CVs</h2>
        <span className="count-badge">{candidates.length}</span>
      </div>

      <div className="cv-body">
        <div className="cv-scale" aria-hidden="true">
          <div className="cv-scale-track" />
          <div className="cv-scale-marker" style={{ top: `${markerTop}%` }}>
            <span className="marker-score">{selected.score}</span>
          </div>
        </div>

        <div className="cv-list">
          {candidates.map((c) => {
            const status = emailStatus[c.id];
            return (
              <div
                key={c.id}
                className={"cv-card" + (c.id === selectedId ? " active" : "")}
                onClick={() => onSelect(c.id)}
              >
                <div className="cv-preview">
                  <embed src={c.file} type="application/pdf" />
                </div>
                <div className="cv-card-footer">
                  <div>
                    <div className="cv-name">{c.name}</div>
                    <div className="cv-sub">{c.years} yrs experience</div>
                  </div>
                  <ScoreChip score={c.score} />
                </div>
                {status && (
                  <span className={`status-tag ${status}`}>
                    {status === "sent" ? "Email sent" : "Declined"}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
