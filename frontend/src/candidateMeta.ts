/**
 * Display metadata for a candidate.
 *
 * The backend never extracts names: `NEVER_EXTRACT` in the profile schema makes
 * protected attributes structurally unrepresentable, so the scorer and the
 * solver cannot read one even by accident. Names here are reconstructed from
 * the CV filename purely so a human can tell the cards apart.
 */

import { cvPdfUrl, cvThumbUrl } from "./api";

const NAME_OVERRIDES: Record<string, string> = {
  cv10_tomas_hidalgo: "Tomás Hidalgo",
  cv7_daniel_kwan: "Daniel Tuovio",
};

/** Real inboxes for demoing the send flow — everyone else stays synthetic. */
const EMAIL_OVERRIDES: Record<string, string> = {
  cv7_daniel_kwan: "notmicrosoft@email.com",
};

/** `cv4_aisha_rahman` -> `Aisha Rahman`. Works for any CV dropped in later. */
export function deriveName(candidateId: string): string {
  const override = NAME_OVERRIDES[candidateId];
  if (override) return override;
  return candidateId
    .replace(/^cv[_-]?\d*[_-]?/i, "")
    .split(/[_\-\s]+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ")
    .trim() || candidateId;
}

export function firstNameOf(candidateId: string): string {
  return deriveName(candidateId).split(" ")[0];
}

/**
 * Where to send the candidate's email. A demo override wins, then the address
 * the backend read out of the CV text (`Profile.contact_email`, never scored),
 * and only a CV with no address at all falls back to a synthetic one built
 * from the filename.
 */
export function emailFor(candidateId: string, contactEmail: string | null | undefined): string {
  return (
    EMAIL_OVERRIDES[candidateId] ??
    contactEmail ??
    `${deriveName(candidateId).toLowerCase().replace(/\s+/g, ".")}@example.com`
  );
}

export function isSyntheticEmail(
  candidateId: string,
  contactEmail: string | null | undefined,
): boolean {
  return !(candidateId in EMAIL_OVERRIDES) && !contactEmail;
}

export interface CandidateAssets {
  pdfUrl: string;
  thumbUrl: string;
}

/**
 * Where a candidate's PDF and first-page PNG live. The demo pool ships inside
 * the frontend build under /assets/cvs; anything uploaded through the app is
 * held by the API and served from there (`PoolRow.has_pdf` says which).
 */
export function assetsFor(candidateId: string, hasPdf = false): CandidateAssets {
  if (hasPdf) {
    return { pdfUrl: cvPdfUrl(candidateId), thumbUrl: cvThumbUrl(candidateId) };
  }
  const stem = encodeURIComponent(candidateId);
  return {
    pdfUrl: `/assets/cvs/${stem}.pdf`,
    thumbUrl: `/assets/cvs/${stem}.png`,
  };
}

/** Fallback tile text when a CV has no pre-rendered PNG (e.g. a fresh upload). */
export function initialsOf(candidateId: string): string {
  return deriveName(candidateId)
    .split(" ")
    .map((w) => w.charAt(0).toUpperCase())
    .slice(0, 2)
    .join("");
}
