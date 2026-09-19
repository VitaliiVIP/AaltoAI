import type { Candidate, EmailStatus } from "../types";

interface EmailPanelProps {
  candidate: Candidate;
  status?: EmailStatus;
  onSend: (id: string) => void;
  onDecline: (id: string) => void;
}

export default function EmailPanel({ candidate, status, onSend, onDecline }: EmailPanelProps) {
  const isAccept = candidate.email.kind === "accept";
  const disabled = Boolean(status);

  return (
    <section className="col col-email" aria-label="Candidate email">
      <div className="col-header">
        <h2>Candidate Email</h2>
      </div>

      <div className="email-body">
        <div className="email-meta">
          To: {candidate.name.toLowerCase().replace(/\s+/g, ".")}@example.com
        </div>
        <div className="email-subject">{candidate.email.subject}</div>

        {/* key forces remount so the draft resets per candidate */}
        <textarea
          key={candidate.id}
          className="email-textarea"
          defaultValue={candidate.email.body}
          disabled={disabled}
        />

        <div className="email-actions">
          <button className="btn btn-primary" disabled={disabled} onClick={() => onSend(candidate.id)}>
            {isAccept ? "Send" : "Send rejection + recourse"}
          </button>
          <button className="btn btn-secondary" disabled={disabled} onClick={() => onDecline(candidate.id)}>
            Decline
          </button>
        </div>

        {status === "sent" && <p className="email-sent-note">✓ Email sent to {candidate.name}</p>}
        {status === "declined" && <p className="email-declined-note">Draft discarded — no email sent</p>}
      </div>
    </section>
  );
}
