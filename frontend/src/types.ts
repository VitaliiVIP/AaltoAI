export type ScoreTier = "green" | "yellow" | "red";

// "sent" = accepted and a confirmation/recourse email went out.
// "declined" = kept for further review, no email sent.
// "rejected" = declined and the rejection email actually went out — a real
// email like "sent", but never an acceptance, regardless of the backend's
// pass/fail decision.
export type EmailStatus = "sent" | "declined" | "rejected";

export interface EmailDraft {
  subject: string;
  body: string;
}

/**
 * The colours mean decision outcomes, not score bands — a fixed 80/50 split
 * would be wrong the moment mode B moves the bar.
 *
 * red = fails a knockout, so no weighted score could rescue it
 * green = advances
 * yellow = clears the hard requirements but misses the bar
 */
export function tierOf(r: { knockouts_passed: boolean; passed: boolean }): ScoreTier {
  if (!r.knockouts_passed) return "red";
  return r.passed ? "green" : "yellow";
}
