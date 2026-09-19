import { useEffect, useMemo, useState } from "react";
import type { PoolRow } from "../apiTypes";
import type { EmailStatus } from "../types";
import { assetsFor, deriveName } from "../candidateMeta";

interface AcceptedDrawerProps {
  open: boolean;
  pool: PoolRow[];
  emailStatus: Record<string, EmailStatus>;
  onClose: () => void;
  onUnaccept: (id: string) => void;
}

/**
 * Everyone who cleared the bar and was actually accepted (Accept button in
 * the Email panel), not just everyone who passed screening. Declining here
 * doesn't reject them — it clears their status and drops them back into the
 * normal applicant pool, where they hit the Accept/Decline choice again.
 */
export default function AcceptedDrawer({
  open,
  pool,
  emailStatus,
  onClose,
  onUnaccept,
}: AcceptedDrawerProps) {
  const [viewing, setViewing] = useState<string | null>(null);

  const accepted = useMemo(
    () => pool.filter((row) => row.decision === "advance" && emailStatus[row.candidate_id] === "sent"),
    [pool, emailStatus],
  );

  useEffect(() => {
    if (!open) setViewing(null);
  }, [open]);

  useEffect(() => {
    if (!viewing) return;
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setViewing(null);
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [viewing]);

  return (
    <>
      <div className={"overlay" + (open ? " visible" : "")} onClick={onClose} />
      <aside
        className={"settings-drawer left" + (open ? " open" : "")}
        aria-label="Accepted applicants"
        aria-hidden={!open}
      >
        <div className="drawer-header">
          <h2>Accepted applicants</h2>
          <button className="icon-btn" aria-label="Close" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="drawer-body">
          {accepted.length === 0 && (
            <p className="empty-note">No one has been accepted yet.</p>
          )}

          <div className="accepted-grid">
            {accepted.map((row) => {
              const name = deriveName(row.candidate_id);
              const { thumbUrl } = assetsFor(row.candidate_id);
              return (
                <div className="accepted-card" key={row.candidate_id}>
                  <button
                    className="accepted-thumb"
                    onClick={() => setViewing(row.candidate_id)}
                    aria-label={`Open ${name}'s CV`}
                  >
                    <img src={thumbUrl} alt={`${name} CV`} />
                  </button>
                  <div className="accepted-name">{name}</div>
                  <div className="accepted-score">{row.score} pts</div>
                  <button
                    className="btn btn-secondary"
                    onClick={() => onUnaccept(row.candidate_id)}
                  >
                    Decline
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      </aside>

      {viewing && (
        <div className="cv-modal-overlay" onClick={() => setViewing(null)}>
          <div className="cv-modal" onClick={(e) => e.stopPropagation()}>
            <button
              className="icon-btn cv-modal-close"
              aria-label="Close CV"
              onClick={() => setViewing(null)}
            >
              ✕
            </button>
            <img src={assetsFor(viewing).thumbUrl} alt={`${deriveName(viewing)} full CV`} />
          </div>
        </div>
      )}
    </>
  );
}
