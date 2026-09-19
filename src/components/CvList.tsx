import { useEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent, KeyboardEvent as ReactKeyboardEvent } from "react";
import type { Candidate, EmailStatus } from "../types";
import ScoreChip from "./ScoreChip";

interface CvListProps {
  candidates: Candidate[];
  selectedId: string;
  emailStatus: Record<string, EmailStatus>;
  onSelect: (id: string) => void;
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

export default function CvList({ candidates, selectedId, emailStatus, onSelect }: CvListProps) {
  const selected = candidates.find((c) => c.id === selectedId) ?? candidates[0];

  const [dragging, setDragging] = useState(false);
  const [dragScore, setDragScore] = useState<number | null>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const cardRefs = useRef<Record<string, HTMLDivElement | null>>({});

  // Refs mirror the latest state so the native (non-passive) wheel listener,
  // which is only attached once, never reads stale values from a closure.
  const selectedIdRef = useRef(selectedId);
  const selectedScoreRef = useRef(selected.score);
  const dragScoreRef = useRef<number | null>(dragScore);
  const wheelTimeoutRef = useRef<number | null>(null);

  useEffect(() => {
    selectedIdRef.current = selectedId;
  }, [selectedId]);

  useEffect(() => {
    selectedScoreRef.current = selected.score;
  }, [selected.score]);

  useEffect(() => {
    dragScoreRef.current = dragScore;
  }, [dragScore]);

  // Keep the card list in sync with the scale: whenever selection changes —
  // by drag, wheel, keyboard, or a direct card click — scroll the matching
  // card into view instead of leaving the list wherever it was.
  useEffect(() => {
    cardRefs.current[selectedId]?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [selectedId]);

  // Candidates sorted high -> low score, for keyboard step navigation.
  const sortedByScore = useMemo(
    () => [...candidates].sort((a, b) => b.score - a.score),
    [candidates]
  );

  function nearestCandidateToScore(score: number): Candidate {
    return candidates.reduce((best, c) =>
      Math.abs(c.score - score) < Math.abs(best.score - score) ? c : best
    );
  }

  function scoreFromClientY(clientY: number): number {
    const rect = trackRef.current!.getBoundingClientRect();
    const percent = clamp((clientY - rect.top) / rect.height, 0, 1);
    return Math.round(100 - percent * 100); // top = 100 (green), bottom = 0 (red)
  }

  function updateFromClientY(clientY: number) {
    const score = scoreFromClientY(clientY);
    setDragScore(score);
    const nearest = nearestCandidateToScore(score);
    if (nearest.id !== selectedId) onSelect(nearest.id);
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
    const index = sortedByScore.findIndex((c) => c.id === selectedId);
    if (e.key === "ArrowUp" || e.key === "ArrowRight") {
      e.preventDefault();
      const next = sortedByScore[clamp(index - 1, 0, sortedByScore.length - 1)];
      onSelect(next.id);
    } else if (e.key === "ArrowDown" || e.key === "ArrowLeft") {
      e.preventDefault();
      const next = sortedByScore[clamp(index + 1, 0, sortedByScore.length - 1)];
      onSelect(next.id);
    }
  }

  // Scrolling/wheeling over the bar nudges the marker and jumps selection to
  // whichever candidate's score is nearest — e.g. scroll to ~46 and it
  // snaps to the 44/100 candidate. Attached as a real DOM listener (not
  // React's onWheel) with { passive: false } so preventDefault actually
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

      const base = dragScoreRef.current ?? selectedScoreRef.current;
      const next = Math.round(clamp(base - delta * WHEEL_SENSITIVITY, 0, 100));

      setDragScore(next);
      setDragging(true);

      const nearest = nearestCandidateToScore(next);
      if (nearest.id !== selectedIdRef.current) onSelect(nearest.id);

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candidates, onSelect]);

  const displayScore = dragScore ?? selected.score;
  const markerTop = 100 - displayScore; // green(top)=100 score, red(bottom)=0 score

  return (
    <section className="col col-cvs" aria-label="Uploaded CVs">
      <div className="col-header">
        <h2>Uploaded CVs</h2>
        <span className="count-badge">{candidates.length}</span>
      </div>

      <div className="cv-body">
        <div
          className={"cv-scale" + (dragging ? " dragging" : "")}
          ref={trackRef}
          role="slider"
          tabIndex={0}
          aria-label="Filter candidates by match score"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={selected.score}
          aria-valuetext={`${selected.name}, ${selected.score} out of 100`}
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
            const status = emailStatus[c.id];
            return (
              <div
                key={c.id}
                ref={(el) => {
                  cardRefs.current[c.id] = el;
                }}
                className={"cv-card" + (c.id === selectedId ? " active" : "")}
                onClick={() => onSelect(c.id)}
              >
                <div className="cv-preview">
                  <img src={c.thumbnail} alt={`${c.name} CV`} />
                </div>
                <div className="cv-card-footer">
                  <div>
                    <div className="cv-name">{c.name}</div>
                    <div className="cv-sub">{c.years} yrs experience</div>
                  </div>
                  <ScoreChip score={c.score} />
                </div>
                {c.score < 80 && c.weakReasons && (
                  <ul className="weak-reasons">
                    <li>{c.weakReasons[0]}</li>
                    <li>{c.weakReasons[1]}</li>
                  </ul>
                )}
                {status && (
                  <span className={`status-tag ${status}`}>
                    {status === "sent" ? "Email sent" : "Kept further"}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
