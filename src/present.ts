/**
 * Every backend -> view mapping, as pure functions. Components stay dumb so the
 * whole translation is reviewable in one place.
 */
import type {
  Delta,
  Envelope,
  Explanation,
  FeatureContribution,
  JobSummary,
  PoolRow,
  Route,
  ScreenResult,
} from "./apiTypes";
import { deriveName, firstNameOf } from "./candidateMeta";
import type { EmailDraft } from "./types";

// --------------------------------------------------------------------------
// Value formatting
// --------------------------------------------------------------------------

/**
 * Everything the backend types as `Any` arrives here as `unknown`. This is the
 * single narrowing point — nothing else should interpolate a wire value.
 */
export function fmtValue(v: unknown, unit = ""): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "number") {
    if (unit === "months") return `${v} mo`;
    return unit ? `${v} ${unit}` : String(v);
  }
  if (typeof v === "string") return v;
  return JSON.stringify(v);
}

function numberOf(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function envNumber(e: Envelope | undefined): number | null {
  return e ? numberOf(e.value) : null;
}

/** Years of experience, one decimal. Total first, software as a fallback. */
export function yearsOf(result: ScreenResult): string {
  const exp = result.profile.experience;
  const months = envNumber(exp.total_months) ?? envNumber(exp.software_months);
  return months == null ? "—" : (Math.round((months / 12) * 10) / 10).toFixed(1);
}

export function yearsOfRow(row: PoolRow): string {
  const months = numberOf(row.total_months) ?? numberOf(row.software_months);
  return months == null ? "—" : (Math.round((months / 12) * 10) / 10).toFixed(1);
}

export function shortId(id: string): string {
  return id.slice(0, 8);
}

// --------------------------------------------------------------------------
// Job configuration
// --------------------------------------------------------------------------

/**
 * The top of the scale, derivable before anything has been screened.
 *
 * Since the job is authored as a point budget this is the budget itself, so a
 * score reads as a percentage. It is still summed rather than assumed: a
 * weight-authored job (the toy fixture, or an older file) is still valid and
 * will not total 100.
 */
export function maxScoreOf(job: JobSummary): number {
  return Object.values(job.score).reduce((sum, f) => sum + f.points, 0);
}

/**
 * Ranks recomputed client-side with the pessimistic tie rule (an equal score
 * counts as ahead), matching `recourse.ranking_mode._rank_of` so a card and its
 * detail panel can never disagree.
 */
export function ranksFor(pool: PoolRow[]): Map<string, number> {
  const qualified = pool.filter((r) => r.knockouts_passed);
  const out = new Map<string, number>();
  for (const row of qualified) {
    out.set(row.candidate_id, qualified.filter((o) => o.score >= row.score).length);
  }
  return out;
}

// --------------------------------------------------------------------------
// Contributions -> matched / gaps
// --------------------------------------------------------------------------

export interface Pill {
  path: string;
  phrase: string;
  detail: string;
  points: number;
}

/**
 * `absent_prior` credits score for something the CV never stated, so those are
 * deliberately excluded here — listing them as "matched" would be a false
 * claim. They surface separately via `creditedWithoutEvidence`.
 */
export function matchedPills(r: ScreenResult, job: JobSummary | null): Pill[] {
  return r.feature_contributions
    .filter((c) => c.contribution > 0 && !c.prior_applied)
    .sort((a, b) => b.contribution - a.contribution)
    .map((c) => ({
      path: c.path,
      phrase: c.phrase,
      detail: fmtValue(c.raw_value, job?.score[c.path]?.unit ?? ""),
      points: c.contribution,
    }));
}

export function creditedWithoutEvidence(r: ScreenResult): Pill[] {
  return r.feature_contributions
    .filter((c) => c.prior_applied && c.contribution > 0)
    .map((c) => ({ path: c.path, phrase: c.phrase, detail: "", points: c.contribution }));
}

export interface GapPill extends Pill {
  /** `absent` means the CV simply did not say — a question, not an instruction. */
  unstated: boolean;
  derivation: FeatureContribution["derivation"];
}

export function gapPills(r: ScreenResult, job: JobSummary | null): GapPill[] {
  return r.feature_contributions
    .filter((c) => c.contribution < c.max_contribution)
    .sort(
      (a, b) =>
        b.max_contribution - b.contribution - (a.max_contribution - a.contribution),
    )
    .map((c) => ({
      path: c.path,
      phrase: c.phrase,
      detail: fmtValue(c.raw_value, job?.score[c.path]?.unit ?? ""),
      points: c.max_contribution - c.contribution,
      unstated: c.derivation === "absent",
      derivation: c.derivation,
    }));
}

// --------------------------------------------------------------------------
// Recruiter summary
// --------------------------------------------------------------------------

/**
 * `explanation.text` is addressed to the candidate, which is the wrong voice
 * for the recruiter column, so this line is generated from the decision instead.
 */
export function recruiterSummary(r: ScreenResult, job: JobSummary | null): string {
  const d = r.decision;
  const best = matchedPills(r, job)[0];
  const worst = gapPills(r, job)[0];
  const head = d.passed ? "Advances" : "Not advanced";
  const bar = d.mode === "A" ? "a threshold of" : "a bar of";
  const parts = [`${head} at ${d.score}/${d.max_score} against ${bar} ${d.threshold}.`];
  if (!d.knockouts_passed) {
    const failed = d.knockouts.filter((k) => !k.passed).map((k) => k.rule);
    parts.push(`Fails a hard requirement: ${failed.join("; ")}.`);
  }
  if (best) parts.push(`Strongest: ${best.phrase} (${best.points} pts).`);
  if (worst) parts.push(`Largest shortfall: ${worst.phrase} (−${worst.points} pts).`);
  if (d.mode === "B" && d.rank != null && d.pool_size != null) {
    parts.push(`Ranked ${d.rank} of ${d.pool_size}; top ${d.slots_n} advance.`);
  }
  return parts.join(" ");
}

// --------------------------------------------------------------------------
// Recourse routes
// --------------------------------------------------------------------------

export interface DeltaView {
  deltaId: string;
  /** One sentence from the explanation, LLM-written or templated. */
  sentence: string;
  phrase: string;
  from: string;
  to: string;
  /** True when the CV never mentioned this: a question, not an instruction. */
  unstated: boolean;
  actionability: Delta["actionability"];
  typicalTimeMonths: number | null;
  points: number | null;
}

export interface RouteView {
  routeId: string;
  label: string;
  gain: number;
  newScore: number;
  months: number;
  cost: number;
  flipTested: boolean;
  rank: number | null;
  deltas: DeltaView[];
}

function deltaPoints(d: Delta, job: JobSummary | null): number | null {
  const f = job?.score[d.field];
  if (!f) return null;
  return f.weight * (Math.min(d.to_steps, f.cap) - Math.min(d.from_steps, f.cap));
}

function viewOfRoute(
  route: Route,
  index: number,
  base: number,
  explanation: Explanation | null,
  job: JobSummary | null,
): RouteView {
  const deltas = route.deltas.map((d) => {
    const sentence = explanation?.sentences.find((s) => s.delta_id === d.delta_id)?.sentence;
    return {
      deltaId: d.delta_id,
      sentence:
        sentence ??
        `${d.candidate_phrase}: ${fmtValue(d.from_value, d.unit)} → ${fmtValue(d.to_value, d.unit)}`,
      phrase: d.candidate_phrase,
      from: fmtValue(d.from_value, d.unit),
      to: fmtValue(d.to_value, d.unit),
      unstated: d.derivation_of_current === "absent",
      actionability: d.actionability,
      typicalTimeMonths: d.typical_time_months,
      points: deltaPoints(d, job),
    };
  });
  // Per-delta points are only shown when they reconcile with the route's own
  // arithmetic; otherwise the cap logic here disagrees with the scorer's and a
  // wrong number is worse than none.
  const gain = route.new_score - base;
  const sum = deltas.reduce((n, d) => n + (d.points ?? NaN), 0);
  if (!Number.isFinite(sum) || sum !== gain) {
    for (const d of deltas) d.points = null;
  }
  return {
    routeId: route.route_id,
    label: `Route ${index + 1}`,
    gain,
    newScore: route.new_score,
    months: route.total_time_months,
    cost: route.cost,
    flipTested: route.flip_test_passed,
    rank: route.rank,
    deltas,
  };
}

export function routeViews(r: ScreenResult, job: JobSummary | null): RouteView[] {
  return r.routes.map((route, i) => viewOfRoute(route, i, r.decision.score, r.explanation, job));
}

/** The best-effort route shown when nothing flips the decision in the horizon. */
export function partialProgressView(r: ScreenResult, job: JobSummary | null): RouteView | null {
  const partial = r.no_feasible_path?.partial_progress;
  if (!partial) return null;
  return viewOfRoute(partial, 0, r.decision.score, r.explanation, job);
}

// --------------------------------------------------------------------------
// Email drafts
// --------------------------------------------------------------------------

/**
 * The rejection body embeds `explanation.text` verbatim. That text is already
 * the candidate-facing letter — framing, routes, disclosures, the as-of stamp
 * and the human-review invitation are all owned by `explain/templates.py` and
 * checked by `explain/checker.py`. Paraphrasing it here would break that
 * guarantee.
 */
export function buildDraft(r: ScreenResult, jobTitle: string): EmailDraft {
  const first = firstNameOf(r.candidate_id);
  if (r.decision.passed) {
    return {
      subject: `You're moving forward — ${jobTitle}`,
      body:
        `Hi ${first},\n\nThanks for applying for the ${jobTitle} role. Your application ` +
        `cleared our pre-screen at ${r.decision.score}/${r.decision.max_score}. ` +
        `We'd like to move you to a technical interview — our team will be in touch to ` +
        `arrange a time.\n\nBest,\nHiring Team`,
    };
  }
  return {
    subject: `Update on your application — ${jobTitle}`,
    body: `Hi ${first},\n\n${r.explanation?.text ?? ""}\n\nBest,\nHiring Team`,
  };
}

/** A strong candidate the recruiter chooses to turn down anyway. */
export function declineDraft(candidateId: string, jobTitle: string): EmailDraft {
  const first = firstNameOf(candidateId);
  return {
    subject: `Update on your application — ${jobTitle}`,
    body:
      `Hi ${first},\n\nThank you for applying for the ${jobTitle} role. This isn't about ` +
      `your qualifications — your background is a strong match on paper — we're moving ` +
      `forward with a candidate whose recent experience lines up more closely with an ` +
      `immediate project need.\n\nWe'd welcome you to apply again for future openings.` +
      `\n\nBest,\nHiring Team`,
  };
}

/** The solver's machine-readable reason codes, in recruiter English. */
const NFP_REASONS: Record<string, string> = {
  no_path_within_horizon: "No combination of allowed changes reaches the bar in time.",
  knockout_immutable: "A hard requirement is fixed and cannot be acquired.",
};

export function nfpReason(code: string): string {
  return NFP_REASONS[code] ?? code.replace(/_/g, " ");
}

export { deriveName };
