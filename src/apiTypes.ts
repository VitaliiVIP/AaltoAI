/**
 * Hand-written mirror of the backend wire format
 * (`backend/recourse_screen/schemas.py`, plus the two shapes that exist only as
 * inline dicts in `backend/recourse_screen/api/app.py`).
 *
 * Nothing here is invented: if a field is not returned by the API it does not
 * belong in this file. View models live in `src/types.ts` instead — keeping the
 * two apart is what makes the mapping in `src/present.ts` reviewable.
 *
 * Python `Any` becomes `unknown` rather than `any`, so every value that crosses
 * the wire untyped has to be narrowed (see `fmtValue`) before it is rendered.
 */

export type Derivation =
  | "stated"
  | "computed"
  | "inferred"
  | "absent"
  | "denied"
  | "restated";

export type Confidence = "high" | "medium" | "low";

export type Actionability =
  | "actionable"
  | "conditionally_actionable"
  | "immutable"
  | "protected_never_use";

export type Mode = "A" | "B";

export interface Evidence {
  quote: string;
  start: number | null;
  end: number | null;
  section: string | null;
  verified: boolean | null;
}

export interface Envelope {
  value: unknown;
  derivation: Derivation;
  confidence: Confidence;
  evidence: Evidence[];
}

export interface Role {
  title_raw: string;
  title_canonical: string;
  employer: string | null;
  start: string | null;
  end: string | null;
  date_precision: "month" | "year" | "unknown";
  months: number | null;
  is_backend_role: boolean;
  skills_mentioned: string[];
  primary_skills: string[];
  evidence: Evidence[];
}

export interface Experience {
  roles: Role[];
  total_months: Envelope;
  software_months: Envelope;
  backend_months: Envelope;
  seniority: Envelope;
  num_roles: Envelope;
}

export interface SkillEntry {
  held: Envelope;
  months: Envelope;
  last_used_year: Envelope;
  proficiency: Envelope;
  project_count: Envelope;
  dated: boolean;
}

export interface Project {
  title: string;
  topics: string[];
  skills: string[];
  deployed: boolean | null;
  evidence: Evidence[];
}

export interface Education {
  highest_level: Envelope;
  field: Envelope;
  in_progress: Envelope;
}

export interface Provenance {
  cv_sha256: string;
  source_file: string | null;
  extractor_model: string;
  prompt_version: string;
  taxonomy_version: string;
  extracted_at: string;
}

export interface Profile {
  schema_version: string;
  job_family: string;
  as_of: string;
  provenance: Provenance;
  experience: Experience;
  skills: Record<string, SkillEntry>;
  projects: Project[];
  project_counts_by_topic: Record<string, number>;
  education: Education;
  derived: Record<string, Envelope>;
  unmatched_skills: string[];
  never_extract: string[];
}

export interface KnockoutResult {
  rule: string;
  path: string;
  passed: boolean;
  current_value: unknown;
  actionability: Actionability;
}

export interface FeatureContribution {
  path: string;
  phrase: string;
  steps: number;
  cap: number;
  weight: number;
  contribution: number;
  max_contribution: number;
  raw_value: unknown;
  derivation: Derivation;
  prior_applied: boolean;
}

export interface Decision {
  mode: Mode;
  passed: boolean;
  score: number;
  knockouts_passed: boolean;
  knockouts: KnockoutResult[];
  /** Mode A: the published threshold. Mode B: the bar the candidate had to beat. */
  threshold: number;
  margin_eps: number;
  rank: number | null;
  pool_size: number | null;
  slots_n: number | null;
  max_score: number;
}

export interface Delta {
  delta_id: string;
  field: string;
  from_value: unknown;
  to_value: unknown;
  from_steps: number;
  to_steps: number;
  unit: string;
  derivation_of_current: Derivation;
  candidate_phrase: string;
  typical_time_months: number | null;
  actionability: Actionability;
  cost: number;
}

export interface Route {
  route_id: string;
  deltas: Delta[];
  cost: number;
  total_time_months: number;
  new_score: number;
  flip_test_passed: boolean;
  rank: number | null;
}

export interface ImmutableBlocker {
  field: string;
  rule: string;
  current_value: unknown;
  disclosure: string;
}

export interface NoFeasiblePath {
  reason: string;
  gap_remaining: number;
  partial_progress: Route | null;
}

export interface RestatementHint {
  field: string;
  phrase: string;
  because_of: string;
  zero_cost: boolean;
}

export interface Sentence {
  delta_id: string;
  sentence: string;
}

export interface Explanation {
  text: string;
  sentences: Sentence[];
  checks_passed: boolean;
  /** True when the deterministic templates were used instead of the LLM. */
  fallback_used: boolean;
  check_failures: string[];
  model_version: string;
}

export interface ScreenResult {
  decision_id: string;
  candidate_id: string;
  job_id: string;
  mode: Mode;
  as_of: string;
  versions: Record<string, string>;
  profile: Profile;
  feature_contributions: FeatureContribution[];
  decision: Decision;
  routes: Route[];
  immutable_blockers: ImmutableBlocker[];
  restatement_hints: RestatementHint[];
  no_feasible_path: NoFeasiblePath | null;
  /** Null exactly when the candidate advanced — there is nothing to explain. */
  explanation: Explanation | null;
  aggregate_line: string | null;
  assertions: Record<string, boolean>;
}

export interface ScreenRequest {
  candidate_id?: string;
  cv_text?: string;
  job_id: string;
  mode: Mode;
  N: number | null;
  explain: boolean;
}

export interface Confirmation {
  path: string;
  value: unknown;
}

export interface RestateRequest {
  candidate_id: string;
  job_id: string;
  mode: Mode;
  N: number | null;
  confirmations: Confirmation[];
}

/** One entry of `GET /jobs` — an inline dict in `api/app.py`, not a pydantic model. */
export interface JobFeature {
  phrase: string;
  weight: number;
  cap: number;
  absent_prior: number;
  unit: string;
  step_size: number;
  actionability: Actionability;
  cost_per_step: number | null;
  max_delta: number;
  typical_time_months: number | null;
  is_causal: boolean;
}

export interface JobSummary {
  job_id: string;
  title: string;
  version: string;
  knockouts: string[];
  score: Record<string, JobFeature>;
  mode: {
    A: { threshold: number; margin_eps: number; weight_shrink_rho: number };
    B: { slots_N: number; margin_eps: number; weight_shrink_rho: number };
  };
  dependencies: string[];
  k_routes: number;
  horizon_months: number;
  manifest_version: string;
  protected_never_use: string[];
}

/** One entry of `GET /candidates`. Scored without any LLM call or audit write. */
export interface PoolRow {
  candidate_id: string;
  file: string | null;
  score: number;
  knockouts_passed: boolean;
  rank: number | null;
  decision: "advance" | "not_advanced";
  total_months: unknown;
  software_months: unknown;
  top_gaps: { phrase: string; missed: number; derivation: Derivation }[];
}

export interface AuditSummary {
  chain_ok: boolean;
  count: number;
  first_bad_index: number | null;
}

export interface SendEmailRequest {
  to: string;
  subject: string;
  body: string;
}

export interface SendEmailResult {
  ok: boolean;
  web: string;
}
