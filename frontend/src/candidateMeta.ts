/**
 * Display metadata for a candidate.
 *
 * The backend never extracts names: `NEVER_EXTRACT` in the profile schema makes
 * protected attributes structurally unrepresentable, so the scorer and the
 * solver cannot read one even by accident. Names here are reconstructed from
 * the CV filename purely so a human can tell the cards apart.
 */

const NAME_OVERRIDES: Record<string, string> = {
  cv10_tomas_hidalgo: "Tomás Hidalgo",
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

/** Synthetic — no contact details are ever extracted from a CV. */
export function emailFor(candidateId: string): string {
  return `${deriveName(candidateId).toLowerCase().replace(/\s+/g, ".")}@example.com`;
}

export interface CandidateAssets {
  pdfUrl: string;
  thumbUrl: string;
}

export function assetsFor(candidateId: string): CandidateAssets {
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
