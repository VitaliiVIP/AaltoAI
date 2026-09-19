import type { Mode } from "../apiTypes";

interface ModeControlProps {
  mode: Mode;
  onModeChange: (m: Mode) => void;
  slotsN: number;
  onSlotsNChange: (n: number) => void;
  threshold: number | null;
  poolSize: number;
}

/**
 * Mode belongs in the top bar rather than behind the gear: it changes the
 * decision for every candidate at once. Mode B is the point of the project —
 * recourse advice weakens when the bar is other applicants rather than a
 * published threshold.
 */
export default function ModeControl({
  mode,
  onModeChange,
  slotsN,
  onSlotsNChange,
  threshold,
  poolSize,
}: ModeControlProps) {
  const clamp = (n: number) => Math.min(Math.max(n, 1), Math.max(poolSize, 1));

  return (
    <div className="mode-control">
      <div className="mode-seg" role="group" aria-label="Screening mode">
        <button
          className={"mode-btn" + (mode === "A" ? " active" : "")}
          aria-pressed={mode === "A"}
          onClick={() => onModeChange("A")}
          title="A published, fixed bar. Recourse advice is stable and checkable."
        >
          A · fixed threshold{threshold != null ? ` ${threshold}` : ""}
        </button>
        <button
          className={"mode-btn" + (mode === "B" ? " active" : "")}
          aria-pressed={mode === "B"}
          onClick={() => onModeChange("B")}
          title="The bar is the Nth best applicant in this pool, so advice depends on who else applied."
        >
          B · top N of pool
        </button>
      </div>

      {mode === "B" && (
        <div className="slots-stepper">
          <button aria-label="Fewer slots" onClick={() => onSlotsNChange(clamp(slotsN - 1))}>
            −
          </button>
          <span aria-live="polite">
            N&nbsp;=&nbsp;<strong>{slotsN}</strong>
          </span>
          <button aria-label="More slots" onClick={() => onSlotsNChange(clamp(slotsN + 1))}>
            +
          </button>
        </div>
      )}
    </div>
  );
}
