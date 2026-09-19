import type { CatalogueFeature, KnockoutResult } from "../apiTypes";
import { buildRule, defaultValue, parseRule, ruleFor } from "../rules";
import { fmtValue } from "../present";

interface KnockoutChecklistProps {
  features: CatalogueFeature[];
  knockouts: string[];
  /** Live evaluation for the selected candidate, when there is one. */
  results: KnockoutResult[];
  onToggle: (rule: string, on: boolean) => void;
  onReplace: (oldRule: string, newRule: string) => void;
}

/**
 * Hard requirements as a checklist rather than a rule syntax.
 *
 * The list is the manifest's vocabulary, so a recruiter cannot write a rule for
 * a feature that does not exist, cannot mistype a path, and cannot reach a
 * protected attribute — those are not in `features` at all, and are shown
 * separately as refusals.
 *
 * The warning below the heading is doing real work. A knockout is not a strong
 * preference: it removes a candidate with no way to compensate, and the whole
 * recourse story collapses for anyone it catches. Making that cost visible at
 * the moment of ticking is the cheapest place to say it.
 */
export default function KnockoutChecklist({
  features,
  knockouts,
  results,
  onToggle,
  onReplace,
}: KnockoutChecklistProps) {
  const eligible = features.filter((f) => f.can_knockout && f.knockout_template);

  return (
    <div className="checklist">
      <p className="block-note">
        Checked in full before anything is scored, and never traded off against the
        budget. A candidate who fails one is out — so tick only what the role
        genuinely cannot do without. Everything else belongs in the points below.
      </p>

      <ul className="checklist-items">
        {eligible.map((feature) => {
          const rule = ruleFor(knockouts, feature.path);
          const on = rule != null;
          const parsed = rule ? parseRule(rule) : null;
          const hit = rule ? results.find((k) => k.rule === rule) : undefined;

          return (
            <li key={feature.path} className={on ? "checked" : ""}>
              <label className="check-row">
                <input
                  type="checkbox"
                  checked={on}
                  onChange={(e) =>
                    e.target.checked
                      ? onToggle(buildRule(feature, defaultValue(feature)), true)
                      : onToggle(rule!, false)
                  }
                />
                <span className="check-phrase">{feature.phrase}</span>
              </label>

              {on && (
                <div className="check-detail">
                  {feature.type === "bool" && <span className="cell-note">must have</span>}

                  {feature.type === "int" && (
                    <label className="cell-note">
                      at least{" "}
                      <input
                        className="mini-number"
                        type="number"
                        min={0}
                        step={feature.step_size}
                        value={parsed?.value ?? ""}
                        onChange={(e) =>
                          onReplace(rule!, buildRule(feature, e.target.value || "0"))
                        }
                      />{" "}
                      {feature.unit}
                    </label>
                  )}

                  {feature.type === "ordinal" && (
                    <label className="cell-note">
                      at least{" "}
                      <select
                        value={parsed?.value ?? ""}
                        onChange={(e) => onReplace(rule!, buildRule(feature, e.target.value))}
                      >
                        {(feature.ladder ?? []).map((level) => (
                          <option key={level} value={level}>
                            {level}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}

                  {hit && (
                    <span className={hit.passed ? "ok" : "bad"}>
                      {hit.passed ? "✓" : "✗"} this candidate: {fmtValue(hit.current_value, feature.unit)}
                    </span>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
