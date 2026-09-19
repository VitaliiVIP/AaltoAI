import { useEffect, useState } from "react";
import type { Candidate, EmailStatus } from "../types";
import { JOB } from "../data";

interface EmailPanelProps {
  candidate: Candidate;
  status?: EmailStatus;
  onSend: (id: string) => void;
  onDecline: (id: string) => void;
}

// Candidates who already clear the bar don't have a pre-written rejection —
// generate a plausible one on the fly for the decline flow.
function declineEmailFor(candidate: Candidate) {
  const firstName = candidate.name.split(" ")[0];
  return {
    subject: `Update on your application — ${JOB.title}`,
    body:
      `Hi ${firstName},\n\nThank you for applying for the ${JOB.title} role. This isn't about your qualifications — your background is a strong match on paper — we're moving forward with a candidate whose recent experience lines up more closely with an immediate project need.\n\nWe'd welcome you to apply again for future openings.\n\nBest,\nHiring Team`,
  };
}

export default function EmailPanel({ candidate, status, onSend, onDecline }: EmailPanelProps) {
  const isStrong = candidate.score >= 80;
  const [declining, setDeclining] = useState(false);

  // Reset back to the Accept/Decline choice whenever the selection changes.
  useEffect(() => {
    setDeclining(false);
  }, [candidate.id]);

  const disabled = Boolean(status);

  // Strong candidates start on a big Accept/Decline choice instead of a
  // pre-written email. Accept does nothing for now; Decline drops into an
  // editable rejection draft.
  if (isStrong && !declining && !status) {
    return (
      <section className="col col-email" aria-label="Candidate email">
        <div className="col-header">
          <h2>Candidate Email</h2>
        </div>
        <div className="email-body email-body-choice">
          <p className="choice-hint">
            {candidate.name} clears the bar for this role. Move forward, or decline and explain why.
          </p>
          <div className="accept-decline-row">
            <button className="btn-accept" onClick={() => {}}>
              Accept
            </button>
            <button className="btn-decline" onClick={() => setDeclining(true)}>
              Decline
            </button>
          </div>
        </div>
      </section>
    );
  }

  const draft = isStrong ? declineEmailFor(candidate) : candidate.email;
  const sendLabel = "Send";
  // "Keep further" leaves the door open — the candidate isn't finalised as
  // declined, just held back from this rejection email for now.
  const secondaryLabel = isStrong ? "Cancel" : "Keep further";

  function handleSecondary() {
    if (isStrong) {
      setDeclining(false); // Cancel just backs out — nothing is recorded.
    } else {
      onDecline(candidate.id);
    }
  }

  return (
    <section className="col col-email" aria-label="Candidate email">
      <div className="col-header">
        <h2>Candidate Email</h2>
      </div>

      <div className="email-body">
        <div className="email-meta">
          To: {candidate.name.toLowerCase().replace(/\s+/g, ".")}@example.com
        </div>
        <div className="email-subject">{draft.subject}</div>

        {/* key forces remount so the draft resets per candidate / mode */}
        <textarea
          key={candidate.id + (isStrong ? "-decline" : "")}
          className="email-textarea"
          defaultValue={draft.body}
          disabled={disabled}
        />

        <div className="email-actions">
          <button className="btn btn-primary" disabled={disabled} onClick={() => onSend(candidate.id)}>
            {sendLabel}
          </button>
          <button className="btn btn-secondary" disabled={disabled} onClick={handleSecondary}>
            {secondaryLabel}
          </button>
        </div>

        {status === "sent" && <p className="email-sent-note">✓ Email sent to {candidate.name}</p>}
        {status === "declined" && (
          <p className="email-declined-note">Kept for further review — no email sent</p>
        )}
      </div>
    </section>
  );
}
