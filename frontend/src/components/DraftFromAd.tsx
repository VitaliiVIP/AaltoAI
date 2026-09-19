import { useState } from "react";
import type { JobDraft } from "../apiTypes";

interface DraftFromAdProps {
  draft: JobDraft | null;
  busy: boolean;
  onDraft: (adText: string) => void;
}

/**
 * Paste the advert, get a first draft of the configuration.
 *
 * The model can only propose criteria that already exist in the manifest — the
 * structured-output grammar is built from it — so this cannot invent a
 * criterion and cannot reach a protected attribute. That constraint is why the
 * two result panels below matter more than the draft itself:
 *
 * - **Refused** is what the ad asked for that the system will not use. An ad
 *   saying "recent graduate" gets read, named, and declined in writing. Dropping
 *   it silently would look like agreement.
 * - **No criterion for this** is what the ad asked for that is legitimate but has
 *   nowhere to go. Kafka experience is a real requirement; approximating it with
 *   a feature that means something else is how a screen quietly starts rejecting
 *   the wrong people, so it is reported instead.
 */
export default function DraftFromAd({ draft, busy, onDraft }: DraftFromAdProps) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");

  return (
    <div className="draft-panel">
      {!open && !draft && (
        <button className="secondary-btn" onClick={() => setOpen(true)}>
          Start from a job ad…
        </button>
      )}

      {open && (
        <>
          <label className="block-note" htmlFor="ad-text">
            Paste the advert. Everything it proposes is editable below, and nothing is
            saved until you save it.
          </label>
          <textarea
            id="ad-text"
            rows={10}
            value={text}
            placeholder="Senior Backend Engineer — we are looking for…"
            onChange={(e) => setText(e.target.value)}
          />
          <div className="draft-actions">
            <button
              className="primary-btn"
              disabled={busy || text.trim().length < 40}
              onClick={() => onDraft(text)}
            >
              {busy ? "Reading the ad…" : "Draft the configuration"}
            </button>
            <button className="link-btn" onClick={() => setOpen(false)}>
              cancel
            </button>
          </div>
        </>
      )}

      {draft && (
        <div className="draft-result">
          <button className="link-btn" onClick={() => setOpen((o) => !o)}>
            {open ? "hide the ad" : "paste a different ad"}
          </button>

          {draft.refused.length > 0 && (
            <section className="draft-block refused">
              <h4>Read, and refused</h4>
              <p className="block-note">
                The ad asked for these. They are not available to any job on this
                manifest, so they were not configured.
              </p>
              <ul className="rule-list">
                {draft.refused.map((r) => (
                  <li key={r.path}>
                    “{r.quote}” <span className="cell-note">— {r.reason}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {draft.unmapped.length > 0 && (
            <section className="draft-block">
              <h4>No criterion for this</h4>
              <p className="block-note">
                Legitimate requirements with nothing in the vocabulary to carry them.
                They need a new feature in the manifest before this screen can see
                them — they were not approximated with something else.
              </p>
              <ul className="rule-list">
                {draft.unmapped.map((u) => (
                  <li key={u}>“{u}”</li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
