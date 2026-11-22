import type { Tone } from "@/components/ui";

/** Badge colour for a lead score: 70+ strong, 40-69 maybe, below 40 weak. */
export function scoreTone(score: number | null): Tone {
  if (score === null) return "gray";
  if (score >= 70) return "green";
  if (score >= 40) return "amber";
  return "red";
}
