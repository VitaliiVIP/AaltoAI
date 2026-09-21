import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  getCatalogue,
  getJobSpec,
  isAbortError,
  postPreflight,
} from "./api";
import type { Catalogue, CatalogueFeature, JobSpec, JobSummary, Preflight } from "./apiTypes";

/** Preflight runs on every keystroke in the budget; this keeps it to one request. */
const PREFLIGHT_DEBOUNCE_MS = 250;

export type EditorPhase = "idle" | "loading" | "saving" | "error";

function messageOf(e: unknown): string {
  if (e instanceof ApiError) return `${e.status}: ${e.message}`;
  return e instanceof Error ? e.message : String(e);
}

/**
 * All the state behind the job editor.
 *
 * The one rule worth stating: this hook never computes what the budget *will*
 * be. Snapping a point allocation onto values the scorer can represent lives in
 * `authoring/budget.py`, and `/jobs/preflight` is how we ask. A second
 * implementation here would be a second set of rounding bugs, and the two would
 * disagree exactly when it mattered.
 */
export function useJobEditor(job: JobSummary | null, onSaved: () => void) {
  const [spec, setSpec] = useState<JobSpec | null>(null);
  const [catalogue, setCatalogue] = useState<Catalogue | null>(null);
  const [preflight, setPreflight] = useState<Preflight | null>(null);
  const [phase, setPhase] = useState<EditorPhase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);

  const jobId = job?.job_id ?? "";
  const preflightRef = useRef<AbortController | null>(null);

  // ---- load ---------------------------------------------------------------

  useEffect(() => {
    if (!jobId) return;
    const ac = new AbortController();
    setPhase("loading");
    Promise.all([getJobSpec(jobId, ac.signal), getCatalogue(jobId, ac.signal)])
      .then(([s, c]) => {
        setSpec(s);
        setCatalogue(c);
        setDirty(false);
        setPhase("idle");
      })
      .catch((e: unknown) => {
        if (isAbortError(e)) return;
        setPhase("error");
        setError(messageOf(e));
      });
    return () => ac.abort();
  }, [jobId]);

  // ---- preflight ----------------------------------------------------------

  useEffect(() => {
    if (!spec) return;
    const timer = window.setTimeout(() => {
      preflightRef.current?.abort();
      const ac = new AbortController();
      preflightRef.current = ac;
      postPreflight(spec, ac.signal)
        .then(setPreflight)
        .catch((e: unknown) => {
          if (!isAbortError(e)) setPreflight(null);
        });
    }, PREFLIGHT_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [spec]);

  // ---- edits --------------------------------------------------------------

  const patch = useCallback((fn: (s: JobSpec) => JobSpec) => {
    setSpec((cur) => (cur ? fn(cur) : cur));
    setDirty(true);
  }, []);

  const setPoints = useCallback(
    (path: string, points: number) =>
      patch((s) => ({
        ...s,
        score: {
          ...s.score,
          [path]: { ...s.score[path], points: Math.max(0, points) },
        },
      })),
    [patch],
  );

  const addCriterion = useCallback(
    (feature: CatalogueFeature) =>
      patch((s) =>
        s.score[feature.path]
          ? s
          : {
              ...s,
              score: {
                ...s.score,
                // A new line starts at zero: the budget is already spent, and
                // silently inflating it past 100 would make the preflight shout.
                [feature.path]: { points: 0, cap: feature.default_cap, absent_prior: 0 },
              },
            },
      ),
    [patch],
  );

  const removeCriterion = useCallback(
    (path: string) =>
      patch((s) => {
        const score = { ...s.score };
        delete score[path];
        return { ...s, score };
      }),
    [patch],
  );

  const setCap = useCallback(
    (path: string, cap: number) =>
      patch((s) => ({
        ...s,
        score: { ...s.score, [path]: { ...s.score[path], cap: Math.max(1, cap) } },
      })),
    [patch],
  );

  const toggleKnockout = useCallback(
    (rule: string, on: boolean) =>
      patch((s) => ({
        ...s,
        knockouts: on
          ? s.knockouts.includes(rule)
            ? s.knockouts
            : [...s.knockouts, rule]
          : s.knockouts.filter((r) => r !== rule),
      })),
    [patch],
  );

  /** Replace a knockout in place, so editing its number does not reorder the list. */
  const replaceKnockout = useCallback(
    (oldRule: string, newRule: string) =>
      patch((s) => ({
        ...s,
        knockouts: s.knockouts.map((r) => (r === oldRule ? newRule : r)),
      })),
    [patch],
  );

  const setThreshold = useCallback(
    (threshold: number) => patch((s) => ({ ...s, threshold })),
    [patch],
  );

  const setSlotsN = useCallback((slots_n: number) => patch((s) => ({ ...s, slots_n })), [patch]);

  // ---- actions ------------------------------------------------------------

  // Saving is turned off for the public demo: the site is unauthenticated and
  // the job is shared by every visitor, so `POST /jobs` no longer exists. The
  // button still "saves" — the draft is kept in this session and snapped to
  // what the server said the budget would become, exactly as a real save would
  // have shown it — but nothing is written and the pool is not re-screened.
  const save = useCallback(() => {
    if (!spec) return;
    setError(null);
    if (preflight?.ok) {
      setSpec((cur) =>
        cur
          ? {
              ...cur,
              threshold: preflight.threshold,
              score: Object.fromEntries(
                Object.entries(cur.score).map(([path, line]) => [
                  path,
                  { ...line, points: preflight.allocation[path] ?? line.points },
                ]),
              ),
            }
          : cur,
      );
    }
    setDirty(false);
    setPhase("idle");
    onSaved();
  }, [spec, preflight, onSaved]);

  const revert = useCallback(async () => {
    if (!jobId) return;
    setSpec(await getJobSpec(jobId));
    setDirty(false);
    setError(null);
  }, [jobId]);

  // ---- derived ------------------------------------------------------------

  const byPath = useMemo(() => {
    const out = new Map<string, CatalogueFeature>();
    for (const f of catalogue?.features ?? []) out.set(f.path, f);
    return out;
  }, [catalogue]);

  const allocated = useMemo(
    () => Object.values(spec?.score ?? {}).reduce((n, l) => n + l.points, 0),
    [spec],
  );

  const unused = useMemo(
    () => (catalogue?.features ?? []).filter((f) => !spec?.score[f.path]),
    [catalogue, spec],
  );

  return {
    spec,
    catalogue,
    preflight,
    phase,
    error,
    dirty,
    byPath,
    allocated,
    unused,
    setPoints,
    setCap,
    addCriterion,
    removeCriterion,
    toggleKnockout,
    replaceKnockout,
    setThreshold,
    setSlotsN,
    save,
    revert,
  };
}
