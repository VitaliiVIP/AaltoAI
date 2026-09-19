import { useState } from "react";

// Purely cosmetic demo state — not wired to any real scoring logic.
export interface ScoringSettings {
  model: string;
  temperature: number;
  strictness: number; // 0 = Lenient, 1 = Balanced, 2 = Strict
  weightSkills: number;
  weightExperience: number;
  weightProjects: number;
  weightEducation: number;
  recourseEnabled: boolean;
  anonymisePII: boolean;
  recoursePathCount: number;
}

export const STRICTNESS_LABELS = ["Lenient", "Balanced", "Strict"];

const DEFAULT_SETTINGS: ScoringSettings = {
  model: "Claude Sonnet 4.5",
  temperature: 0.3,
  strictness: 1,
  weightSkills: 40,
  weightExperience: 30,
  weightProjects: 20,
  weightEducation: 10,
  recourseEnabled: true,
  anonymisePII: true,
  recoursePathCount: 3,
};

export function useScoringSettings() {
  const [settings, setSettings] = useState<ScoringSettings>(DEFAULT_SETTINGS);

  function update<K extends keyof ScoringSettings>(key: K, value: ScoringSettings[K]) {
    setSettings((prev) => ({ ...prev, [key]: value }));
  }

  return { settings, update };
}
