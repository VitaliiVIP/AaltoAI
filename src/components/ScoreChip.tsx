import { scoreTier } from "../types";

interface ScoreChipProps {
  score: number;
}

export default function ScoreChip({ score }: ScoreChipProps) {
  return <span className={`score-chip ${scoreTier(score)}`}>{score}/100</span>;
}
