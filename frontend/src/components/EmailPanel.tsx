import { useEffect, useRef, useState } from "react";
import type { ScreenResult } from "../apiTypes";
import type { EmailStatus } from "../types";
import { deriveName, emailFor, isSyntheticEmail } from "../candidateMeta";
import { buildDraft, declineDraft } from "../present";

interface EmailPanelProps {
  result: ScreenResult | null;
  jobTitle: string;
  status?: EmailStatus;
  onSend: (id: string) => void;
  onSendEmail: (id: string, to: string, subject: string, body: string, declined: boolean) => void;
  onDecline: (id: string) => void;
}

export default function EmailPanel({
  result,
  jobTitle,
  status,
  onSend,
  onSendEmail,
  onDecline,
}: EmailPanelProps) {
  const [declining, setDeclining] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const candidateId = result?.candidate_id ?? null;

  // Reset back to the Accept/Decline choice whenever the selection changes.
  useEffect(() => {
    setDeclining(false);
  }, [candidateId]);

  if (!result || !candidateId) {
    return (
      <section className="col col-email" aria-label="Candidate email">
        <div className="col-header">
          <h2>Candidate Email</h2>
        </div>
        <div className="email-body">
          <p className="empty-note">No screening result yet.</p>
        </div>
      </section>
    );
  }

  const name = deriveName(candidateId);
  const to = emailFor(candidateId, result.profile.contact_email);
  const synthetic = isSyntheticEmail(candidateId, result.profile.contact_email);
  const passed = result.decision.passed;
  const disabled = Boolean(status);
  const explanation = result.explanation;

  // Accepted directly (never went through the decline draft) — no email was
  // ever composed, so there's nothing to show but the confirmation.
  if (passed && status === "sent" && !declining) {
    return (
      <section className="col col-email" aria-label="Candidate email">
        <div className="col-header">
          <h2>Candidate Email</h2>
        </div>
        <div className="email-body email-body-choice">
          <p className="choice-hint accepted-hint">✓ {name} has been added to the candidate list.</p>
        </div>
      </section>
    );
  }

  // Candidates who cleared the bar start on a decision rather than a draft.
  if (passed && !declining && !status) {
    return (
      <section className="col col-email" aria-label="Candidate email">
        <div className="col-header">
          <h2>Candidate Email</h2>
        </div>
        <div className="email-body email-body-choice">
          <p className="choice-hint">
            {name} clears the bar for this role at {result.decision.score}/
            {result.decision.max_score}. Move forward, or decline and explain why.
          </p>
          <div className="accept-decline-row">
            <button className="btn-accept" onClick={() => onSend(candidateId)}>
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

  const draft =
    passed && declining ? declineDraft(candidateId, jobTitle) : buildDraft(result, jobTitle);
  const secondaryLabel = passed ? "Cancel" : "Keep further";

  function handleSecondary() {
    if (passed) {
      setDeclining(false); // Cancel just backs out — nothing is recorded.
    } else if (candidateId) {
      onDecline(candidateId);
    }
  }

  function handleSend() {
    if (!candidateId) return;
    // Read the live textarea value, not the original draft — an edit the
    // recruiter made here is what actually goes out over SMTP.
    const body = textareaRef.current?.value ?? draft.body;
    onSendEmail(candidateId, to, draft.subject, body, passed && declining);
  }

  return (
    <section className="col col-email" aria-label="Candidate email">
      <div className="col-header">
        <h2>Candidate Email</h2>
      </div>

      <div className="email-body">
        <div className="email-meta">
          To: {to}
          {synthetic && (
            <span className="synthetic-note"> (synthetic — no address found in the CV)</span>
          )}
        </div>
        <div className="email-subject">{draft.subject}</div>

        {/* Model-written sentences come from the backend's cache of the shipped
            decisions; anything the cache has not seen (an edited job, a
            restated CV) is the checked template text instead. */}
        {!passed && explanation && (
          <div className="provenance-row">
            <span className={"prov-badge " + (explanation.fallback_used ? "template" : "llm")}>
              {explanation.fallback_used ? "template sentences" : "Claude sentences (cached)"}
            </span>
            <span className={"prov-badge " + (explanation.checks_passed ? "ok" : "bad")}>
              {explanation.checks_passed ? "checks passed" : "checks FAILED"}
            </span>
            <span className="prov-version">{explanation.model_version}</span>
          </div>
        )}
        {!passed && explanation && explanation.check_failures.length > 0 && (
          <p className="block-note">Check failures: {explanation.check_failures.join(", ")}</p>
        )}

        {/* key forces a remount when the underlying decision changes, so a new
            explanation actually replaces the text in this uncontrolled textarea
            instead of silently keeping the old draft. */}
        <textarea
          key={`${candidateId}|${result.decision_id}|${passed && declining ? "decline" : "main"}`}
          ref={textareaRef}
          className="email-textarea"
          defaultValue={draft.body}
          disabled={disabled}
        />

        <div className="email-actions">
          <button className="btn btn-primary" disabled={disabled} onClick={handleSend}>
            Send
          </button>
          <button className="btn btn-secondary" disabled={disabled} onClick={handleSecondary}>
            {secondaryLabel}
          </button>
        </div>

        {status === "sent" && <p className="email-sent-note">✓ Email sent to {name}</p>}
        {status === "rejected" && (
          <p className="email-declined-note">✓ Rejection sent to {name}</p>
        )}
        {status === "declined" && (
          <p className="email-declined-note">Kept for further review — no email sent</p>
        )}
      </div>
    </section>
  );
}
