export type ScoreTier = "green" | "yellow" | "red";

export type EmailKind = "accept" | "reject";

export type EmailStatus = "sent" | "declined";

export interface RecourseItem {
  change: string;
  impact: string;
}

export interface EmailDraft {
  kind: EmailKind;
  subject: string;
  body: string;
}

export interface Candidate {
  id: string;
  name: string;
  file: string;
  thumbnail: string;
  score: number;
  years: number;
  matched: string[];
  missing: string[];
  /** The 2 main reasons this candidate is weak for the role. Only set when score < 80. */
  weakReasons?: [string, string];
  summary: string;
  recourse: RecourseItem[];
  email: EmailDraft;
}

export interface JobInfo {
  title: string;
  requirements: string[];
}

export function scoreTier(score: number): ScoreTier {
  if (score >= 80) return "green";
  if (score >= 50) return "yellow";
  return "red";
}
