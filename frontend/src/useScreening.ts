import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  getAudit,
  getCandidates,
  getJobs,
  isAbortError,
  postScreen,
} from "./api";
import type { AuditSummary, JobSummary, Mode, PoolRow, ScreenResult } from "./apiTypes";
import { maxScoreOf } from "./present";

export type Phase = "idle" | "loading" | "error";

/** Debounce before screening: the score scrubber fires a selection per wheel notch. */
const SCREEN_DEBOUNCE_MS = 300;

function messageOf(e: unknown): string {
  if (e instanceof ApiError) return `${e.status}: ${e.message}`;
  return e instanceof Error ? e.message : String(e);
}

function schedule(fn: () => void): void {
  if (typeof window.requestIdleCallback === "function") {
    window.requestIdleCallback(() => fn(), { timeout: 2000 });
  } else {
    window.setTimeout(fn, 200);
  }
}

export function useScreening() {
  const [job, setJob] = useState<JobSummary | null>(null);
  // Mode B is the default: "we interview five" is how hiring actually works, and
  // it is the harder case for recourse, so it should not be the one you opt into.
  const [mode, setMode] = useState<Mode>("B");
  const [slotsN, setSlotsN] = useState<number | null>(null);
  const [pool, setPool] = useState<PoolRow[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [audit, setAudit] = useState<AuditSummary | null>(null);

  const [results, setResults] = useState<Record<string, ScreenResult>>({});

  const [poolPhase, setPoolPhase] = useState<Phase>("loading");
  const [poolError, setPoolError] = useState<string | null>(null);
  const [screenPhase, setScreenPhase] = useState<Phase>("idle");
  const [screenError, setScreenError] = useState<string | null>(null);

  // Refs mirror state for the async paths, which must never read a stale closure.
  const resultsRef = useRef(results);
  resultsRef.current = results;
  const selectedRef = useRef(selectedId);
  selectedRef.current = selectedId;
  /** Joins concurrent requests for the same key — this is what keeps React 18
   *  StrictMode's double-invoked effects from writing two audit records. */
  const inflight = useRef(new Map<string, Promise<ScreenResult>>());
  const controllers = useRef(new Map<string, AbortController>());
  const userBusy = useRef(false);

  const jobId = job?.job_id ?? "";
  const effectiveN = mode === "B" ? slotsN : null;

  const cacheKey = useCallback(
    (candidateId: string) => `${candidateId}|${jobId}|${mode}|${effectiveN ?? ""}`,
    [jobId, mode, effectiveN],
  );

  const maxScore = useMemo(() => (job ? maxScoreOf(job) : 100), [job]);

  // ---- loads -------------------------------------------------------------

  useEffect(() => {
    const ac = new AbortController();
    getJobs(ac.signal)
      .then((js) => {
        const first = js[0] ?? null;
        setJob(first);
        if (first) setSlotsN((n) => n ?? first.mode.B.slots_N);
      })
      .catch((e: unknown) => {
        if (isAbortError(e)) return;
        setPoolPhase("error");
        setPoolError(messageOf(e));
      });
    getAudit(ac.signal)
      .then(setAudit)
      .catch(() => setAudit(null));
    return () => ac.abort();
  }, []);

  const refreshPool = useCallback(async () => {
    if (!jobId) return;
    setPoolPhase("loading");
    setPoolError(null);
    try {
      const rows = await getCandidates({ job: jobId, mode, N: effectiveN });
      setPool(rows);
      setPoolPhase("idle");
      setSelectedId((cur) =>
        cur && rows.some((r) => r.candidate_id === cur) ? cur : (rows[0]?.candidate_id ?? null),
      );
    } catch (e: unknown) {
      if (isAbortError(e)) return;
      setPoolPhase("error");
      setPoolError(messageOf(e));
    }
  }, [jobId, mode, effectiveN]);

  useEffect(() => {
    void refreshPool();
  }, [refreshPool]);

  // Mode or N changes the decision for everyone; drop in-flight work for the
  // old settings. Cached results are keyed by mode+N, so flipping back is free.
  useEffect(() => {
    return () => {
      for (const ac of controllers.current.values()) ac.abort();
      controllers.current.clear();
      inflight.current.clear();
    };
  }, [mode, effectiveN, jobId]);

  // ---- screening ---------------------------------------------------------

  // `explain: true` asks for the model-written sentences the backend has cached
  // for this decision; a miss comes back as templated prose. Neither is a model
  // call, so there is nothing to opt into and one request per key is enough.
  const screenOnce = useCallback(
    (candidateId: string): Promise<ScreenResult> => {
      const key = cacheKey(candidateId);
      const cached = resultsRef.current[key];
      if (cached) return Promise.resolve(cached);

      const joined = inflight.current.get(key);
      if (joined) return joined;

      const ac = new AbortController();
      controllers.current.set(key, ac);
      const p = postScreen(
        { candidate_id: candidateId, job_id: jobId, mode, N: effectiveN, explain: true },
        ac.signal,
      )
        .then((res) => {
          setResults((prev) => ({ ...prev, [key]: res }));
          return res;
        })
        .finally(() => {
          inflight.current.delete(key);
          controllers.current.delete(key);
        });
      inflight.current.set(key, p);
      return p;
    },
    [cacheKey, jobId, mode, effectiveN],
  );

  // Screen the selection, debounced. A cache hit renders synchronously — the
  // timer is only armed on a miss, so revisiting a scrubbed-past candidate is
  // instant.
  useEffect(() => {
    if (!selectedId || !jobId) return;
    if (resultsRef.current[cacheKey(selectedId)]) {
      setScreenPhase("idle");
      setScreenError(null);
      return;
    }
    const timer = window.setTimeout(() => {
      userBusy.current = true;
      setScreenPhase("loading");
      setScreenError(null);
      screenOnce(selectedId)
        .then(() => {
          if (selectedRef.current === selectedId) setScreenPhase("idle");
        })
        .catch((e: unknown) => {
          if (isAbortError(e)) return;
          if (selectedRef.current !== selectedId) return;
          setScreenPhase("error");
          setScreenError(messageOf(e));
        })
        .finally(() => {
          userBusy.current = false;
        });
    }, SCREEN_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [selectedId, jobId, cacheKey, screenOnce]);

  // Warm the rest of the pool while the user reads, so that scrubbing the
  // score scale afterwards is instant.
  useEffect(() => {
    if (!jobId || pool.length === 0) return;
    let cancelled = false;
    function step() {
      if (cancelled) return;
      if (userBusy.current) {
        schedule(step);
        return;
      }
      const next = pool.find((r) => !resultsRef.current[cacheKey(r.candidate_id)]);
      if (!next) return;
      screenOnce(next.candidate_id)
        .catch(() => undefined)
        .finally(() => {
          if (!cancelled) schedule(step);
        });
    }
    schedule(step);
    return () => {
      cancelled = true;
    };
  }, [jobId, pool, cacheKey, screenOnce]);

  // ---- actions -----------------------------------------------------------

  // ---- derived -----------------------------------------------------------

  const key = selectedId ? cacheKey(selectedId) : "";
  const result = key ? (results[key] ?? null) : null;
  const selectedRow = pool.find((r) => r.candidate_id === selectedId) ?? null;

  return {
    job,
    maxScore,
    mode,
    setMode,
    slotsN: slotsN ?? job?.mode.B.slots_N ?? 3,
    setSlotsN,
    pool,
    selectedId,
    setSelectedId,
    selectedRow,
    result,
    audit,
    poolPhase,
    poolError,
    screenPhase,
    screenError,
    refreshPool,
  };
}
