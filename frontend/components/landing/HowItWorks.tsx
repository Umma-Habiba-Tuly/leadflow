"use client";

import { useState } from "react";
import { Badge, Card, cx } from "@/components/ui";
import { scoreTone } from "@/lib/score";

/**
 * Static, fictional previews of each step. Nothing here is real output: the card says so, and every
 * business, address and score below is made up.
 */
const LEADS = [
  { name: "Bright Smile Dental", site: "brightsmile.example", email: "hello@brightsmile.example", score: 82, reason: "Dental clinic in Austin with a 3.6 rating. Room to improve its online presence." },
  { name: "Capital City Orthodontics", site: "capitalortho.example", email: "info@capitalortho.example", score: 74, reason: "Right niche and city, and reachable by email." },
  { name: "Oak Hill Dental", site: "none listed", email: "none found", score: 55, reason: "Right niche and city, but no email found yet. Worth a look." },
  { name: "Quick Auto Repair", site: "quickauto.example", email: "shop@quickauto.example", score: 4, reason: "An auto repair shop, not a dental clinic." },
];

const DRAFT = "Hi Bright Smile Dental team, I'm Sam from Rivera Web Studio. We help dental clinics get more new-patient bookings with a faster, mobile-friendly website. Would it be useful if I sent over two quick ideas for yours?";
const FOOTER = "Sam Rivera\nRivera Web Studio\n--\nRivera Web Studio, 100 Congress Ave, Austin, TX 78701\nDon't want these emails? Unsubscribe here: …";

function Frame({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Card className="h-full overflow-hidden">
      <div className="border-b border-brand-base/10 px-4 py-2.5 text-xs text-brand-ink/65">{label} · example, made-up data</div>
      <div className="p-4">{children}</div>
    </Card>
  );
}

function FindPreview() {
  return (
    <Frame label="Imported leads">
      <ul className="divide-y divide-brand-base/10 text-sm">
        {LEADS.slice(0, 3).map((l) => (
          <li key={l.name} className="flex items-baseline justify-between gap-4 py-2.5">
            <span className="font-medium">{l.name}</span>
            <span className="truncate text-brand-ink/65">{l.email}</span>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs text-brand-ink/65">Duplicates and anyone who has opted out are skipped for you.</p>
    </Frame>
  );
}

function ScorePreview() {
  return (
    <Frame label="Scored leads, best first">
      <ul className="divide-y divide-brand-base/10 text-sm">
        {LEADS.map((l) => (
          <li key={l.name} className="py-2.5">
            <div className="flex items-center justify-between gap-3">
              <span className="font-medium">{l.name}</span>
              <Badge tone={scoreTone(l.score)}>{l.score}</Badge>
            </div>
            <p className="mt-0.5 text-xs text-brand-ink/65">{l.reason}</p>
          </li>
        ))}
      </ul>
    </Frame>
  );
}

function WritePreview() {
  return (
    <Frame label="Draft for Bright Smile Dental">
      <p className="text-xs text-brand-ink/65">Subject</p>
      <p className="mb-3 text-sm font-medium">Website and SEO for Bright Smile Dental</p>
      <p className="text-sm leading-relaxed">{DRAFT}</p>
    </Frame>
  );
}

function ReviewPreview() {
  return (
    <Frame label="Exactly what the recipient will receive">
      <p className="text-sm leading-relaxed">{DRAFT}</p>
      <pre className="mt-3 whitespace-pre-wrap rounded-lg border border-brand-base/10 bg-brand-page p-3 text-xs leading-relaxed text-brand-ink/75">{FOOTER}</pre>
      <p className="mt-2 text-xs text-brand-ink/65">Your name, address and the unsubscribe link are added automatically and cannot be removed.</p>
    </Frame>
  );
}

function SendPreview() {
  return (
    <Frame label="Preview before sending">
      <p className="mb-2 text-sm font-medium">These 2 emails would be sent:</p>
      <ul className="divide-y divide-brand-base/10 rounded-lg border border-brand-base/10 text-sm">
        {LEADS.slice(0, 2).map((l) => (
          <li key={l.name} className="px-3 py-2"><span className="font-medium">{l.email}</span><span className="block text-xs text-brand-ink/65">Website and SEO for {l.name}</span></li>
        ))}
      </ul>
      <p className="mt-3 text-xs text-brand-ink/65">Nothing is sent until you confirm. Real emails cannot be unsent.</p>
    </Frame>
  );
}

const STEPS = [
  { key: "find", label: "Find", title: "Bring a list, or search Google Maps.",
    points: ["Import a CSV, or search by kind of business and place.", "Missing emails are looked for on the business's own website, politely.", "Duplicates and opted-out addresses are skipped automatically."], Preview: FindPreview },
  { key: "score", label: "Score", title: "Every lead is ranked against your offer.",
    points: ["A score from 0 to 100 and a one-line reason you can check.", "The best leads are listed first.", "Wrong niche or wrong city scores low."], Preview: ScorePreview },
  { key: "write", label: "Write", title: "A draft for each lead worth contacting.",
    points: ["Written from the facts we have, not invented ones.", "No links, no fake reply subjects, no leftover placeholders.", "You can edit anything."], Preview: WritePreview },
  { key: "review", label: "Review", title: "Nothing goes out unless you approve it.",
    points: ["Approve emails one at a time. There is no approve-all.", "See the full email, footer included, before you decide.", "Edit a draft after approving and it needs approving again."], Preview: ReviewPreview },
  { key: "send", label: "Send", title: "Preview first, then send from your own mailbox.",
    points: ["See exactly which emails would go out, then confirm.", "A daily limit per mailbox, and anyone who unsubscribed is skipped.", "Sent from your own address, so replies reach you."], Preview: SendPreview },
] as const;

export function HowItWorks() {
  const [active, setActive] = useState<(typeof STEPS)[number]["key"]>("find");
  const step = STEPS.find((s) => s.key === active)!;
  const { Preview } = step;
  return (
    <div id="how">
      <div role="tablist" aria-label="How LeadFlow works" className="mx-auto flex max-w-full flex-wrap justify-center gap-1">
        {STEPS.map((s, i) => (
          <button key={s.key} role="tab" id={`tab-${s.key}`} aria-selected={active === s.key} aria-controls="how-panel" onClick={() => setActive(s.key)}
            className={cx("rounded-lg px-3.5 py-1.5 text-sm font-medium transition-colors", active === s.key ? "bg-brand-base/[0.07] text-brand-ink" : "text-brand-ink/65 hover:text-brand-ink")}>
            <span className="mr-1.5 text-brand-ink/65">{i + 1}</span>{s.label}
          </button>
        ))}
      </div>
      <div id="how-panel" role="tabpanel" aria-labelledby={`tab-${active}`} className="mx-auto mt-6 grid max-w-5xl gap-4 md:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        <div className="p-2 md:pr-8 md:pt-6">
          <h3 className="text-2xl leading-snug">{step.title}</h3>
          <ul className="mt-5 space-y-3 text-brand-ink/75">
            {step.points.map((p) => (
              <li key={p} className="flex gap-3"><span aria-hidden className="mt-2.5 size-1 shrink-0 rounded-full bg-brand-ink/40" />{p}</li>
            ))}
          </ul>
        </div>
        <Preview />
      </div>
    </div>
  );
}
