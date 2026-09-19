import type { ScoreTier } from "../types";

interface ScoreChipProps {
  score: number;
  max: number;
  tier: ScoreTier;
}

export default function ScoreChip({ score, max, tier }: ScoreChipProps) {
  return (
    <span className={`score-chip ${tier}`}>
      {score}/{max}
    </span>
  );
}
