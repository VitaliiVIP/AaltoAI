import { useEffect, useMemo, useState } from "react";
import type { PoolRow } from "../apiTypes";
import type { EmailStatus } from "../types";
import { assetsFor, deriveName } from "../candidateMeta";

interface AcceptedDrawerProps {
  open: boolean;
  pool: PoolRow[];
  emailStatus: Record<string, EmailStatus>;
  onClose: () => void;
  onRemove: (id: string) => void;
}

/**
 * Everyone currently in play: candidates who cleared the bar and were
 * actually accepted (Accept), and candidates who didn't clear it but were
 * kept for further review instead of rejected (Keep further) — both are one
 * click away from the Email panel's draft, neither is a final decision yet.
 * Declining here doesn't reject them — it clears their status and drops
 * them back into the normal applicant pool.
 */
export default function AcceptedDrawer({
  open,
  pool,
  emailStatus,
  onClose,
  onRemove,
}: AcceptedDrawerProps) {
  const [viewing, setViewing] = useState<string | null>(null);

  const shown = useMemo(
    () =>
      pool
        .map((row) => ({ row, status: emailStatus[row.candidate_id] }))
        .filter(
          ({ row, status }) =>
            (status === "sent" && row.decision === "advance") || status === "declined",
        ),
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
        aria-label="Candidates in play"
        aria-hidden={!open}
      >
        <div className="drawer-header">
          <h2>Candidates in play</h2>
          <button className="icon-btn" aria-label="Close" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="drawer-body">
          {shown.length === 0 && (
            <p className="empty-note">No one accepted or kept for further review yet.</p>
          )}

          <div className="accepted-grid">
            {shown.map(({ row, status }) => {
              const name = deriveName(row.candidate_id);
              const { thumbUrl } = assetsFor(row.candidate_id);
              const accepted = status === "sent";
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
                  <span className={"status-tag" + (accepted ? " sent" : "")}>
                    {accepted ? "Accepted" : "Kept further"}
                  </span>
                  <button
                    className="btn btn-secondary"
                    onClick={() => onRemove(row.candidate_id)}
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
