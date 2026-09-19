import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  getAudit,
  getCandidates,
  getJobs,
  isAbortError,
  postExtract,
  postRestate,
  postScreen,
} from "./api";
import type { AuditSummary, JobSummary, Mode, PoolRow, ScreenResult } from "./apiTypes";
import { maxScoreOf } from "./present";

export type Phase = "idle" | "loading" | "explaining" | "error";

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
  const [mode, setMode] = useState<Mode>("A");
  const [slotsN, setSlotsN] = useState<number | null>(null);
  const [pool, setPool] = useState<PoolRow[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [audit, setAudit] = useState<AuditSummary | null>(null);

  const [results, setResults] = useState<Record<string, ScreenResult>>({});
  /** Pre-restatement results, so the before/after is reversible. */
  const [originals, setOriginals] = useState<Record<string, ScreenResult>>({});

  const [poolPhase, setPoolPhase] = useState<Phase>("loading");
  const [poolError, setPoolError] = useState<string | null>(null);
  const [screenPhase, setScreenPhase] = useState<Phase>("idle");
  const [screenError, setScreenError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

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

  const screenOnce = useCallback(
    (candidateId: string, explain: boolean): Promise<ScreenResult> => {
      const key = cacheKey(candidateId);
      const slot = explain ? `${key}|llm` : key;
      const cached = resultsRef.current[key];
      if (!explain && cached) return Promise.resolve(cached);

      const joined = inflight.current.get(slot);
      if (joined) return joined;

      const ac = new AbortController();
      controllers.current.set(slot, ac);
      const p = postScreen(
        { candidate_id: candidateId, job_id: jobId, mode, N: effectiveN, explain },
        ac.signal,
      )
        .then((res) => {
          setResults((prev) => ({ ...prev, [key]: res }));
          return res;
        })
        .finally(() => {
          inflight.current.delete(slot);
          controllers.current.delete(slot);
        });
      inflight.current.set(slot, p);
      return p;
    },
    [cacheKey, jobId, mode, effectiveN],
  );

  // Screen the selection, debounced. A cache hit renders synchronously — the
  // timer is only armed on a miss, so revisiting a scrubbed-past candidate is
  // instant. `explain: false` returns complete templated prose with no LLM call.
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
      screenOnce(selectedId, false)
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

  // Warm the rest of the pool while the user reads. With `explain: false` this
  // costs no LLM calls, and afterwards scrubbing the score scale is instant.
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
      screenOnce(next.candidate_id, false)
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

  /** The only path that spends an LLM call: re-run with the verbaliser on. */
  const polishExplanation = useCallback(async () => {
    if (!selectedId) return;
    setScreenPhase("explaining");
    setScreenError(null);
    userBusy.current = true;
    try {
      await screenOnce(selectedId, true);
      setScreenPhase("idle");
    } catch (e: unknown) {
      if (!isAbortError(e)) {
        setScreenPhase("error");
        setScreenError(messageOf(e));
      }
    } finally {
      userBusy.current = false;
    }
  }, [selectedId, screenOnce]);

  const applyRestatement = useCallback(
    async (paths: string[]) => {
      if (!selectedId || paths.length === 0) return;
      const key = cacheKey(selectedId);
      const current = resultsRef.current[key];
      if (!current) return;
      setScreenPhase("loading");
      setScreenError(null);
      userBusy.current = true;
      try {
        const next = await postRestate(
          {
            candidate_id: selectedId,
            job_id: jobId,
            mode,
            N: effectiveN,
            confirmations: paths.map((p) => ({ path: p, value: true })),
          },
          { parentDecisionId: current.decision_id, explain: false },
        );
        setOriginals((prev) => (prev[key] ? prev : { ...prev, [key]: current }));
        setResults((prev) => ({ ...prev, [key]: next }));
        setScreenPhase("idle");
      } catch (e: unknown) {
        if (!isAbortError(e)) {
          setScreenPhase("error");
          setScreenError(messageOf(e));
        }
      } finally {
        userBusy.current = false;
      }
    },
    [selectedId, cacheKey, jobId, mode, effectiveN],
  );

  const revertRestatement = useCallback(() => {
    if (!selectedId) return;
    const key = cacheKey(selectedId);
    const original = originals[key];
    if (!original) return;
    setResults((prev) => ({ ...prev, [key]: original }));
    setOriginals((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  }, [selectedId, cacheKey, originals]);

  const uploadCv = useCallback(
    async (file: File) => {
      setUploading(true);
      try {
        const { candidate_id } = await postExtract(file);
        await refreshPool();
        setSelectedId(candidate_id);
        return candidate_id;
      } finally {
        setUploading(false);
      }
    },
    [refreshPool],
  );

  // ---- derived -----------------------------------------------------------

  const key = selectedId ? cacheKey(selectedId) : "";
  const result = key ? (results[key] ?? null) : null;
  const restatedFrom = key ? (originals[key] ?? null) : null;
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
    restatedFrom,
    audit,
    poolPhase,
    poolError,
    screenPhase,
    screenError,
    uploading,
    refreshPool,
    polishExplanation,
    applyRestatement,
    revertRestatement,
    uploadCv,
  };
}
