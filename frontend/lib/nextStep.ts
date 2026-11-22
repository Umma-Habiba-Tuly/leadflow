import type { CampaignStats } from "@/lib/types";

export type StepKey = "leads" | "enrich" | "score" | "draft" | "review" | "send";

/**
 * Which pipeline step deserves the dark button right now. A wrong answer misleads people, so this
 * is a pure function with tests for every state.
 *
 * Order: leads, then missing emails (a lead's email affects its score), score, write, review, send.
 * Writing needs the sender details, so without them we skip it rather than point at a disabled button.
 */
export function nextStep(stats: CampaignStats, profileComplete: boolean): StepKey | null {
  if (stats.leads === 0) return "leads";
  if (stats.to_enrich > 0) return "enrich";
  if (stats.to_score > 0) return "score";
  if (stats.to_draft > 0 && profileComplete) return "draft";
  if (stats.to_review > 0) return "review";
  if (stats.to_send > 0) return "send";
  return null;
}
