import { describe, expect, it } from "vitest";
import { nextStep } from "@/lib/nextStep";
import type { CampaignStats } from "@/lib/types";

const stats = (over: Partial<CampaignStats> = {}): CampaignStats => ({
  leads: 0, with_email: 0, scored: 0, drafts: 0, approved: 0, sent: 0, opted_out: 0,
  to_enrich: 0, to_score: 0, to_draft: 0, to_review: 0, to_send: 0, ...over,
});

describe("nextStep: which button gets the dark style", () => {
  it("empty campaign: bring in leads", () => expect(nextStep(stats(), true)).toBe("leads"));
  it("a lead with a website but no email: find the email first", () => expect(nextStep(stats({ leads: 3, to_enrich: 1, to_score: 3 }), true)).toBe("enrich"));
  it("leads waiting to be scored", () => expect(nextStep(stats({ leads: 3, to_score: 3 }), true)).toBe("score"));
  it("scored leads with no drafts yet: write", () => expect(nextStep(stats({ leads: 3, scored: 3, to_draft: 2 }), true)).toBe("draft"));
  it("won't point at Write while the sender details are missing (that button is disabled)", () => {
    expect(nextStep(stats({ leads: 3, scored: 3, to_draft: 2 }), false)).toBeNull();
  });
  it("drafts nobody has approved yet: review", () => expect(nextStep(stats({ leads: 3, scored: 3, drafts: 2, to_review: 2 }), true)).toBe("review"));
  it("review stays next until every draft is approved", () => expect(nextStep(stats({ leads: 3, scored: 3, drafts: 3, approved: 2, to_review: 1, to_send: 2 }), true)).toBe("review"));
  it("everything approved: send", () => expect(nextStep(stats({ leads: 3, scored: 3, drafts: 2, approved: 2, to_send: 2 }), true)).toBe("send"));
  it("all done: nothing is highlighted", () => expect(nextStep(stats({ leads: 3, scored: 3, drafts: 2, approved: 0, sent: 2 }), true)).toBeNull());

  it("earlier steps win over later ones", () => {
    expect(nextStep(stats({ leads: 5, to_enrich: 1, to_score: 5, to_draft: 2, drafts: 3, to_review: 1, to_send: 1 }), true)).toBe("enrich");
    expect(nextStep(stats({ leads: 5, to_score: 5, to_draft: 2, drafts: 3, to_review: 1, to_send: 1 }), true)).toBe("score");
  });
});

describe("nextStep: states found by the tests themselves", () => {
  it("after everything is sent, Review is not pointed at again (sent drafts are not 'approved' any more)", () => {
    expect(nextStep(stats({ leads: 3, scored: 3, drafts: 2, approved: 0, sent: 2, to_review: 0, to_send: 0 }), true)).toBeNull();
  });
  it("an approved draft whose address was refused is not 'waiting to send'", () => {
    expect(nextStep(stats({ leads: 3, scored: 3, drafts: 2, approved: 1, sent: 1, to_send: 0 }), true)).toBeNull();
  });
});
