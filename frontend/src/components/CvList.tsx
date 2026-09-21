import { useEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent, KeyboardEvent as ReactKeyboardEvent } from "react";
import type { Mode, PoolRow } from "../apiTypes";
import type { EmailStatus } from "../types";
import { tierOf } from "../types";
import { assetsFor, deriveName, initialsOf } from "../candidateMeta";
import { ranksFor, yearsOfRow } from "../present";
import type { Phase } from "../useScreening";
import ScoreChip from "./ScoreChip";

interface CvListProps {
  pool: PoolRow[];
  mode: Mode;
  maxScore: number;
  selectedId: string | null;
  emailStatus: Record<string, EmailStatus>;
  aggregateLine: string | null;
  phase: Phase;
  error: string | null;
  onSelect: (id: string) => void;
  onRetry: () => void;
  onDelete: (id: string) => void;
}

function clamp(n: number, min: number, max: number) {
  return Math.min(max, Math.max(min, n));
}

// One wheel "notch" is usually reported as deltaY ~100 (deltaMode 0, pixel mode).
// Trackpads report much smaller, more frequent deltas in the same mode, which
// naturally yields smoother scrubbing. Line/page modes are normalised to roughly
// the same feel so a single notch moves a handful of score points, not the whole bar.
const WHEEL_SENSITIVITY = 0.12;
const WHEEL_SETTLE_MS = 220;

export default function CvList({
  pool,
  mode,
  maxScore,
  selectedId,
  emailStatus,
  aggregateLine,
  phase,
  error,
  onSelect,
  onRetry,
  onDelete,
}: CvListProps) {
  const [viewMode, setViewMode] = useState<"active" | "sent">("active");

  // "Active" = genuinely untouched — no decision made yet. The moment a CV
  // is Accepted or Kept further it belongs to the "Candidates in play"
  // drawer instead, so it leaves this list entirely, not just the "sent"
  // half of it. "Sent" here only ever means a real email actually went out —
  // that includes an actual rejection ("rejected"), not just an acceptance.
  const filteredPool = useMemo(
    () =>
      pool.filter((c) => {
        const status = emailStatus[c.candidate_id];
        return viewMode === "sent" ? status === "sent" || status === "rejected" : !status;
      }),
    [pool, emailStatus, viewMode],
  );

  const selected = filteredPool.find((c) => c.candidate_id === selectedId) ?? filteredPool[0] ?? null;

  const activeCount = useMemo(
    () => pool.filter((c) => !emailStatus[c.candidate_id]).length,
    [pool, emailStatus],
  );
  const sentCount = useMemo(
    () =>
      pool.filter((c) => {
        const status = emailStatus[c.candidate_id];
        return status === "sent" || status === "rejected";
      }).length,
    [pool, emailStatus],
  );

  const [dragging, setDragging] = useState(false);
  const [dragScore, setDragScore] = useState<number | null>(null);
  const [brokenThumbs, setBrokenThumbs] = useState<Record<string, boolean>>({});
  const trackRef = useRef<HTMLDivElement>(null);
  const cardRefs = useRef<Record<string, HTMLDivElement | null>>({});

  // Refs mirror the latest state so the native (non-passive) wheel listener,
  // which is only attached once, never reads stale values from a closure.
  const selectedIdRef = useRef(selectedId);
  const selectedScoreRef = useRef(selected?.score ?? 0);
  const dragScoreRef = useRef<number | null>(dragScore);
  const maxScoreRef = useRef(maxScore);
  const poolRef = useRef(filteredPool);
  const wheelTimeoutRef = useRef<number | null>(null);

  selectedIdRef.current = selectedId;
  selectedScoreRef.current = selected?.score ?? 0;
  dragScoreRef.current = dragScore;
  maxScoreRef.current = maxScore;
  poolRef.current = filteredPool;

  // Keep the card list in sync with the scale: whenever selection changes —
  // by drag, wheel, keyboard, or a direct card click — scroll the matching
  // card into view instead of leaving the list wherever it was.
  useEffect(() => {
    if (selectedId) cardRefs.current[selectedId]?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [selectedId]);

  // Candidates sorted high -> low score, for keyboard step navigation and
  // rendering. Ranks stay based on the whole pool (not just this view) so
  // switching tabs never shuffles everyone else's rank number.
  const sortedByScore = useMemo(
    () => [...filteredPool].sort((a, b) => b.score - a.score),
    [filteredPool],
  );
  const ranks = useMemo(() => ranksFor(pool), [pool]);

  function nearestCandidateToScore(score: number, rows: PoolRow[]): PoolRow | null {
    if (rows.length === 0) return null;
    return rows.reduce((best, c) =>
      Math.abs(c.score - score) < Math.abs(best.score - score) ? c : best,
    );
  }

  function scoreFromClientY(clientY: number): number {
    const rect = trackRef.current!.getBoundingClientRect();
    const percent = clamp((clientY - rect.top) / rect.height, 0, 1);
    return Math.round(maxScore * (1 - percent)); // top = max (green), bottom = 0 (red)
  }

  function updateFromClientY(clientY: number) {
    const score = scoreFromClientY(clientY);
    setDragScore(score);
    const nearest = nearestCandidateToScore(score, filteredPool);
    if (nearest && nearest.candidate_id !== selectedId) onSelect(nearest.candidate_id);
  }

  function handlePointerDown(e: ReactPointerEvent<HTMLDivElement>) {
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    setDragging(true);
    updateFromClientY(e.clientY);
  }

  function handlePointerMove(e: ReactPointerEvent<HTMLDivElement>) {
    if (!dragging) return;
    updateFromClientY(e.clientY);
  }

  function endDrag(e: ReactPointerEvent<HTMLDivElement>) {
    if ((e.target as HTMLElement).hasPointerCapture?.(e.pointerId)) {
      (e.target as HTMLElement).releasePointerCapture(e.pointerId);
    }
    setDragging(false);
    setDragScore(null);
  }

  function handleKeyDown(e: ReactKeyboardEvent<HTMLDivElement>) {
    const index = sortedByScore.findIndex((c) => c.candidate_id === selectedId);
    if (index < 0) return;
    if (e.key === "ArrowUp" || e.key === "ArrowRight") {
      e.preventDefault();
      onSelect(sortedByScore[clamp(index - 1, 0, sortedByScore.length - 1)].candidate_id);
    } else if (e.key === "ArrowDown" || e.key === "ArrowLeft") {
      e.preventDefault();
      onSelect(sortedByScore[clamp(index + 1, 0, sortedByScore.length - 1)].candidate_id);
    }
  }

  // Scrolling/wheeling over the bar nudges the marker and jumps selection to
  // whichever candidate's score is nearest. Attached as a real DOM listener
  // (not React's onWheel) with { passive: false } so preventDefault actually
  // stops the page from scrolling underneath the bar.
  useEffect(() => {
    const el = trackRef.current;
    if (!el) return;

    function handleWheelNative(e: WheelEvent) {
      e.preventDefault();

      // Normalise so one notch (~100px in pixel mode) or one "line" moves
      // roughly the same amount, and clamp bursts from inertial trackpads.
      const rawDelta = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY;
      const delta = clamp(rawDelta, -120, 120);

      const max = maxScoreRef.current;
      const base = dragScoreRef.current ?? selectedScoreRef.current;
      const next = Math.round(clamp(base - delta * WHEEL_SENSITIVITY, 0, max));

      setDragScore(next);
      setDragging(true);

      const nearest = nearestCandidateToScore(next, poolRef.current);
      if (nearest && nearest.candidate_id !== selectedIdRef.current) onSelect(nearest.candidate_id);

      if (wheelTimeoutRef.current) window.clearTimeout(wheelTimeoutRef.current);
      wheelTimeoutRef.current = window.setTimeout(() => {
        setDragging(false);
        setDragScore(null);
      }, WHEEL_SETTLE_MS);
    }

    el.addEventListener("wheel", handleWheelNative, { passive: false });
    return () => {
      el.removeEventListener("wheel", handleWheelNative);
      if (wheelTimeoutRef.current) window.clearTimeout(wheelTimeoutRef.current);
    };
  }, [onSelect]);

  const displayScore = dragScore ?? selected?.score ?? 0;
  const markerTop = maxScore > 0 ? 100 * (1 - displayScore / maxScore) : 100;

  return (
    <section className="col col-cvs" aria-label="Applicant CVs">
      <div className="col-header">
        <h2>Applicant CVs</h2>
        <span className="count-badge">{filteredPool.length}</span>

        <div className="view-toggle" role="tablist" aria-label="Show active or answered CVs">
          <button
            role="tab"
            aria-selected={viewMode === "active"}
            aria-label={`Active (${activeCount})`}
            title={`Active (${activeCount})`}
            className={"view-toggle-circle check" + (viewMode === "active" ? " active" : "")}
            onClick={() => setViewMode("active")}
          >
            ✓
          </button>
          <button
            role="tab"
            aria-selected={viewMode === "sent"}
            aria-label={`Sent (${sentCount})`}
            title={`Sent (${sentCount})`}
            className={"view-toggle-circle cross" + (viewMode === "sent" ? " active" : "")}
            onClick={() => setViewMode("sent")}
          >
            ✕
          </button>
        </div>
      </div>

      {mode === "B" && aggregateLine && <p className="aggregate-line">{aggregateLine}</p>}

      {phase === "error" && (
        <div className="panel-error">
          <p>{error}</p>
          <button className="btn btn-secondary" onClick={onRetry}>
            Retry
          </button>
        </div>
      )}

      <div className="cv-body">
        <div
          className={"cv-scale" + (dragging ? " dragging" : "")}
          ref={trackRef}
          role="slider"
          tabIndex={0}
          aria-label="Filter candidates by match score"
          aria-valuemin={0}
          aria-valuemax={maxScore}
          aria-valuenow={selected?.score ?? 0}
          aria-valuetext={
            selected
              ? `${deriveName(selected.candidate_id)}, ${selected.score} out of ${maxScore}`
              : "no candidates"
          }
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          onKeyDown={handleKeyDown}
        >
          <div className="cv-scale-track" />
          <div className="cv-scale-marker" style={{ top: `${markerTop}%` }}>
            <span className="marker-score">{displayScore}</span>
          </div>
        </div>

        <div className="cv-list">
          {sortedByScore.map((c) => {
            const status = emailStatus[c.candidate_id];
            const name = deriveName(c.candidate_id);
            const { thumbUrl } = assetsFor(c.candidate_id, c.has_pdf);
            const rank = ranks.get(c.candidate_id) ?? null;
            const tier = tierOf({
              knockouts_passed: c.knockouts_passed,
              passed: c.decision === "advance",
            });
            return (
              <div
                key={c.candidate_id}
                ref={(el) => {
                  cardRefs.current[c.candidate_id] = el;
                }}
                className={"cv-card" + (c.candidate_id === selectedId ? " active" : "")}
                onClick={() => onSelect(c.candidate_id)}
              >
                <div className="cv-preview">
                  {brokenThumbs[c.candidate_id] ? (
                    <div className="thumb-fallback" aria-hidden="true">
                      {initialsOf(c.candidate_id)}
                    </div>
                  ) : (
                    <img
                      src={thumbUrl}
                      alt={`${name} CV`}
                      onError={() =>
                        setBrokenThumbs((prev) => ({ ...prev, [c.candidate_id]: true }))
                      }
                    />
                  )}
                </div>
                <div className="cv-card-footer">
                  <div>
                    <div className="cv-name">
                      {mode === "B" && rank != null && <span className="rank-badge">#{rank}</span>}
                      {name}
                    </div>
                    <div className="cv-sub">{yearsOfRow(c)} yrs experience</div>
                  </div>
                  <ScoreChip score={c.score} max={maxScore} tier={tier} />
                </div>
                {!c.knockouts_passed && (
                  <span className="status-tag ko">Fails a hard requirement</span>
                )}
                {c.decision !== "advance" && c.top_gaps.length > 0 && (
                  <ul className="weak-reasons">
                    {c.top_gaps.map((g) => (
                      <li key={g.phrase}>
                        {g.phrase} <span className="gap-points">−{g.missed}</span>
                        {g.derivation === "absent" && <span className="unstated-flag"> · not stated</span>}
                      </li>
                    ))}
                  </ul>
                )}
                {status && (
                  <span className={`status-tag ${status}`}>
                    {status === "sent"
                      ? "Email sent"
                      : status === "rejected"
                        ? "Rejection sent"
                        : "Kept further"}
                  </span>
                )}
                {viewMode === "sent" && (
                  <button
                    className="btn btn-secondary cv-delete-btn"
                    onClick={(e) => {
                      e.stopPropagation(); // don't also select the card underneath
                      onDelete(c.candidate_id);
                    }}
                  >
                    Delete
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
