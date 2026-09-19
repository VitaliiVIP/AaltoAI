import { useEffect, useState } from "react";
import type { ScreenResult } from "../apiTypes";
import { shortId } from "../present";

interface RestateDrawerProps {
  open: boolean;
  result: ScreenResult | null;
  restatedFrom: ScreenResult | null;
  busy: boolean;
  onClose: () => void;
  onConfirm: (paths: string[]) => void;
  onRevert: () => void;
}

/**
 * The candidate's side of the screen: the letter they would receive, plus the
 * structured right-to-correct channel (GDPR Art. 16). Confirming a hint is
 * deterministic and costs no LLM call.
 */
export default function RestateDrawer({
  open,
  result,
  restatedFrom,
  busy,
  onClose,
  onConfirm,
  onRevert,
}: RestateDrawerProps) {
  const [checked, setChecked] = useState<Record<string, boolean>>({});

  useEffect(() => {
    setChecked({});
  }, [result?.candidate_id, result?.decision_id]);

  const hints = result?.restatement_hints ?? [];
  const selected = Object.entries(checked)
    .filter(([, v]) => v)
    .map(([k]) => k);

  return (
    <>
      <div className={"overlay" + (open ? " visible" : "")} onClick={onClose} />
      <aside
        className={"settings-drawer candidate-drawer" + (open ? " open" : "")}
        aria-label="Candidate view"
        aria-hidden={!open}
      >
        <div className="drawer-header">
          <h2>Candidate view</h2>
          <button className="icon-btn" aria-label="Close" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="drawer-body">
          {!result && <p className="empty-note">No screening result yet.</p>}

          {result && (
            <>
              {restatedFrom && (
                <div className="restated-chip">
                  Restated from decision {shortId(restatedFrom.decision_id)}
                  <button className="link-btn" onClick={onRevert}>
                    ← back to original screen
                  </button>
                </div>
              )}

              <section className="drawer-section">
                <h3>The letter this candidate would receive</h3>
                {result.explanation ? (
                  <pre className="candidate-letter">{result.explanation.text}</pre>
                ) : (
                  <p className="empty-note">
                    This candidate advanced — there is no rejection to explain.
                  </p>
                )}
              </section>

              <section className="drawer-section">
                <h3>Things we may have missed</h3>
                <p className="block-note">
                  A screen can only read what the CV says. Confirming something you already have
                  costs nothing and re-runs the decision immediately. Confirmations apply to this
                  screening only — they are not written back to the stored profile.
                </p>
                {hints.length === 0 && <p className="empty-note">Nothing to confirm.</p>}
                {hints.map((h) => (
                  <label className="hint-row" key={h.field}>
                    <input
                      type="checkbox"
                      checked={Boolean(checked[h.field])}
                      onChange={(e) =>
                        setChecked((prev) => ({ ...prev, [h.field]: e.target.checked }))
                      }
                    />
                    <span>
                      {h.phrase}
                      <span className="hint-because">
                        {h.because_of === "not mentioned"
                          ? " (not mentioned on your CV)"
                          : ` (likely, since you listed ${h.because_of})`}
                      </span>
                    </span>
                  </label>
                ))}
                {hints.length > 0 && (
                  <button
                    className="btn btn-primary"
                    disabled={busy || selected.length === 0}
                    onClick={() => onConfirm(selected)}
                  >
                    {busy ? "Re-running…" : "Confirm & re-run"}
                  </button>
                )}
              </section>
            </>
          )}
        </div>
      </aside>
    </>
  );
}
