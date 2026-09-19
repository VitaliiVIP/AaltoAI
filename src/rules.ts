/**
 * Reading and writing knockout rules for the checklist.
 *
 * A rule is `path op value` — the same three-token grammar `Knockout.parse` in
 * `schemas.py` accepts. This file exists so the UI can offer a checkbox and a
 * number field instead of a text box; the backend still parses and validates
 * whatever comes back, and `/jobs/preflight` is what decides whether a rule is
 * acceptable. Nothing here is authoritative.
 */
import type { CatalogueFeature } from "./apiTypes";

export interface ParsedRule {
  path: string;
  op: string;
  value: string;
}

const RULE_RE = /^\s*([\w.]+)\s*(==|>=|<=|>|<)\s*(\S+)\s*$/;

export function parseRule(rule: string): ParsedRule | null {
  const m = RULE_RE.exec(rule);
  return m ? { path: m[1], op: m[2], value: m[3] } : null;
}

/** The rule a tick produces for this feature at this value. */
export function buildRule(feature: CatalogueFeature, value: string | number | boolean): string {
  if (feature.type === "bool") return `${feature.path} == ${value ? "true" : "false"}`;
  return `${feature.path} >= ${value}`;
}

/** The rule currently in force for a feature, if any. */
export function ruleFor(knockouts: string[], path: string): string | null {
  return knockouts.find((r) => parseRule(r)?.path === path) ?? null;
}

/**
 * The requirement in recruiter English, e.g. "at least 12 months" or "required".
 * Used as the checkbox label so the rule string never has to be the interface.
 */
/** A sensible starting value for a newly ticked requirement. */
export function defaultValue(feature: CatalogueFeature): string {
  if (feature.type === "bool") return "true";
  if (feature.type === "ordinal") {
    const ladder = feature.ladder ?? [];
    return ladder[Math.floor(ladder.length / 2)] ?? "";
  }
  return String(feature.step_size * 2);
}
