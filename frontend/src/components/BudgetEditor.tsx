import { useState } from "react";
import type { CatalogueFeature, JobSpec, Preflight } from "../apiTypes";

interface BudgetEditorProps {
  spec: JobSpec;
  byPath: Map<string, CatalogueFeature>;
  unused: CatalogueFeature[];
  allocated: number;
  budgetTotal: number;
  preflight: Preflight | null;
  /** The phrase in the job ad that justified each criterion, when drafted. */
  quotes: Record<string, string>;
  onPoints: (path: string, points: number) => void;
  onCap: (path: string, cap: number) => void;
  onAdd: (feature: CatalogueFeature) => void;
  onRemove: (path: string) => void;
}

/** Full marks in the feature's own unit, so nobody has to think in solver steps. */
function fullMarks(feature: CatalogueFeature | undefined, cap: number | null): string {
  if (!feature) return "";
  const steps = cap ?? feature.default_cap;
  if (feature.type === "bool") return "yes";
  if (feature.type === "ordinal") return (feature.ladder ?? [])[steps] ?? String(steps);
  return `${steps * feature.step_size} ${feature.unit}`;
}

/**
 * The point budget: one row per criterion, one hundred points to spend.
 *
 * Spending a fixed budget rather than setting free-floating weights is the whole
 * idea. It forces the trade-off to be explicit — more for Kubernetes means less
 * for something else — and it makes the resulting score a percentage of the job
 * rather than a number whose meaning depends on the scale it was drawn from.
 *
 * What a criterion can be worth is not continuous. A criterion reaching full
 * marks in eight steps can only be worth multiples of eight, because the engine
 * needs whole points per step. The server does that snapping and reports it
 * back; the "applied" note on a row is where a recruiter sees it happen.
 */
export default function BudgetEditor({
  spec,
  byPath,
  unused,
  allocated,
  budgetTotal,
  preflight,
  quotes,
  onPoints,
  onCap,
  onAdd,
  onRemove,
}: BudgetEditorProps) {
  const [adding, setAdding] = useState(false);
  const remaining = budgetTotal - allocated;
  const rows = Object.entries(spec.score).sort((a, b) => b[1].points - a[1].points);

  return (
    <div className="budget">
      <div className={"budget-meter" + (remaining === 0 ? " balanced" : "")}>
        <div className="meter-track">
          <div
            className="meter-fill"
            style={{ width: `${Math.min(100, (allocated / budgetTotal) * 100)}%` }}
          />
        </div>
        <span aria-live="polite">
          <strong>{allocated}</strong> of {budgetTotal} allocated
          {remaining !== 0 && (
            <em className="meter-note">
              {remaining > 0 ? ` · ${remaining} unspent` : ` · ${-remaining} over`}
            </em>
          )}
        </span>
      </div>

      <table className="config-table budget-table">
        <thead>
          <tr>
            <th>Criterion</th>
            <th className="num">Points</th>
            <th>Full marks at</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map(([path, line]) => {
            const feature = byPath.get(path);
            const adjusted = preflight?.adjusted?.[path];
            const step = line.cap ?? feature?.default_cap ?? 1;
            return (
              <tr key={path}>
                <td>
                  {/* The phrase, not the path: a recruiter is picking a criterion,
                      not addressing a feature. The path stays in the Review tab. */}
                  <span className="criterion-phrase">{feature?.phrase ?? path}</span>
                  {quotes[path] && <div className="quote-note">“{quotes[path]}”</div>}
                  {line.absent_prior > 0 && (
                    <span className="cell-note">absent prior {line.absent_prior}</span>
                  )}
                </td>
                <td className="num">
                  <input
                    className="points-input"
                    type="number"
                    min={0}
                    max={budgetTotal}
                    step={step}
                    value={line.points}
                    aria-label={`Points for ${feature?.phrase ?? path}`}
                    onChange={(e) => onPoints(path, Number(e.target.value))}
                  />
                  {adjusted && adjusted.applied !== adjusted.asked && (
                    <div className="cell-note adjusted">→ {adjusted.applied} applied</div>
                  )}
                </td>
                <td>
                  {feature && feature.type === "int" ? (
                    <label className="cell-note">
                      <input
                        className="mini-number"
                        type="number"
                        min={feature.step_size}
                        step={feature.step_size}
                        value={(line.cap ?? feature.default_cap) * feature.step_size}
                        aria-label={`Full marks for ${feature.phrase}`}
                        onChange={(e) =>
                          onCap(path, Math.max(1, Math.round(Number(e.target.value) / feature.step_size)))
                        }
                      />{" "}
                      {feature.unit}
                    </label>
                  ) : feature && feature.type === "ordinal" ? (
                    <select
                      value={(feature.ladder ?? [])[line.cap ?? feature.default_cap] ?? ""}
                      onChange={(e) =>
                        onCap(path, Math.max(1, (feature.ladder ?? []).indexOf(e.target.value)))
                      }
                    >
                      {(feature.ladder ?? []).slice(1).map((level) => (
                        <option key={level} value={level}>
                          {level}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <span className="cell-note">{fullMarks(feature, line.cap)}</span>
                  )}
                </td>
                <td>
                  <button
                    className="link-btn"
                    aria-label={`Remove ${feature?.phrase ?? path}`}
                    onClick={() => onRemove(path)}
                  >
                    remove
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {adding ? (
        <div className="add-criterion">
          <select
            autoFocus
            defaultValue=""
            aria-label="Add a criterion"
            onChange={(e) => {
              const feature = unused.find((f) => f.path === e.target.value);
              if (feature) onAdd(feature);
              setAdding(false);
            }}
          >
            <option value="" disabled>
              Pick a criterion…
            </option>
            {unused.map((f) => (
              <option key={f.path} value={f.path}>
                {f.phrase}
              </option>
            ))}
          </select>
          <button className="link-btn" onClick={() => setAdding(false)}>
            cancel
          </button>
        </div>
      ) : (
        <button className="link-btn" disabled={unused.length === 0} onClick={() => setAdding(true)}>
          + add a criterion
        </button>
      )}

      {preflight && preflight.problems.length > 0 && (
        <ul className="problem-list">
          {preflight.problems.map((p) => (
            <li key={p} className="bad">
              {p}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
