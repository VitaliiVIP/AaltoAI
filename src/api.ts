import type {
  AuditSummary,
  Catalogue,
  JobDraft,
  JobSpec,
  JobSummary,
  PoolRow,
  Preflight,
  Profile,
  RestateRequest,
  ScreenRequest,
  ScreenResult,
} from "./apiTypes";

// Vite proxies /api -> http://127.0.0.1:8000 (see vite.config.ts), so the
// client stays base-URL-free in dev. The env var is the escape hatch for
// `vite preview` or running the backend on another host.
const BASE = import.meta.env.VITE_API_BASE ?? "/api";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly body: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** True for a fetch aborted by us — callers must ignore these, not render them. */
export function isAbortError(e: unknown): boolean {
  return e instanceof DOMException && e.name === "AbortError";
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    // FastAPI's HTTPException detail is genuinely the most useful message here
    // (a 404 from /screen lists the candidate ids it does know about).
    let message = body;
    try {
      const parsed: unknown = JSON.parse(body);
      if (parsed && typeof parsed === "object" && "detail" in parsed) {
        message = String((parsed as { detail: unknown }).detail);
      }
    } catch {
      /* body was not JSON; use it as-is */
    }
    throw new ApiError(message || `${res.status} ${res.statusText}`, res.status, body);
  }
  return (await res.json()) as T;
}

function postJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  return req<T>(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
}

export function getJobs(signal?: AbortSignal): Promise<JobSummary[]> {
  return req<JobSummary[]>("/jobs", { signal });
}

export function getCandidates(
  p: { job: string; mode: string; N?: number | null },
  signal?: AbortSignal,
): Promise<PoolRow[]> {
  const q = new URLSearchParams({ job: p.job, mode: p.mode });
  if (p.N != null) q.set("N", String(p.N));
  return req<PoolRow[]>(`/candidates?${q}`, { signal });
}

export function postScreen(body: ScreenRequest, signal?: AbortSignal): Promise<ScreenResult> {
  return postJson<ScreenResult>("/screen", body, signal);
}

export function postRestate(
  body: RestateRequest,
  opts: { parentDecisionId: string; explain: boolean },
  signal?: AbortSignal,
): Promise<ScreenResult> {
  // parent_decision_id and explain are query params on this endpoint, not body fields.
  const q = new URLSearchParams({
    parent_decision_id: opts.parentDecisionId,
    explain: String(opts.explain),
  });
  return postJson<ScreenResult>(`/restate?${q}`, body, signal);
}

export function postExtract(
  file: File,
  signal?: AbortSignal,
): Promise<{ candidate_id: string; profile: Profile }> {
  const form = new FormData();
  form.append("file", file);
  // No explicit content-type: the browser has to set the multipart boundary.
  return req<{ candidate_id: string; profile: Profile }>("/extract", {
    method: "POST",
    body: form,
    signal,
  });
}

// ---- authoring -----------------------------------------------------------

/** Everything a job can be built out of, including what the manifest refuses. */
export function getCatalogue(job?: string, signal?: AbortSignal): Promise<Catalogue> {
  const q = job ? `?job=${encodeURIComponent(job)}` : "";
  return req<Catalogue>(`/catalogue${q}`, { signal });
}

export function getJobSpec(jobId: string, signal?: AbortSignal): Promise<JobSpec> {
  return req<JobSpec>(`/jobs/${encodeURIComponent(jobId)}/spec`, { signal });
}

/** What the budget would become, and what is wrong with it. Saves nothing. */
export function postPreflight(spec: JobSpec, signal?: AbortSignal): Promise<Preflight> {
  return postJson<Preflight>("/jobs/preflight", spec, signal);
}

export function postJobSave(spec: JobSpec, signal?: AbortSignal): Promise<JobSummary> {
  return postJson<JobSummary>("/jobs", spec, signal);
}

/** The one authoring call that spends an LLM call. Returns a proposal, not a job. */
export function postJobDraft(
  body: { ad_text: string; threshold?: number; slots_n?: number },
  signal?: AbortSignal,
): Promise<JobDraft> {
  return postJson<JobDraft>("/jobs/draft", body, signal);
}

export function getAudit(signal?: AbortSignal): Promise<AuditSummary> {
  return req<AuditSummary>("/audit", { signal });
}

export const auditUrl = (decisionId: string) =>
  `${BASE}/audit/${encodeURIComponent(decisionId)}`;
