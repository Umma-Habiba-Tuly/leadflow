"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Button, Field, Input, Modal, cx } from "@/components/ui";
import { api } from "@/lib/api";
import { nextStep } from "@/lib/nextStep";
import type {
  Campaign, CampaignStats, Draft, DraftSummary, EnrichResult, ImportResult, LeadList, Mailbox, ScoreSummary, SentEmail,
} from "@/lib/types";
import { DraftsPanel } from "./DraftsPanel";
import { LeadsTable } from "./LeadsTable";
import { SendModal } from "./SendModal";
import { SentTable } from "./SentTable";

type Tab = "leads" | "drafts" | "sent";
type Notice = { tone: "green" | "amber" | "red"; text: string } | null;

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

function importNotice(r: ImportResult): Notice {
  const skipped = [
    r.skipped_duplicates && `${plural(r.skipped_duplicates, "duplicate")}`,
    r.skipped_invalid && `${r.skipped_invalid} invalid`,
    r.skipped_suppressed && `${r.skipped_suppressed} opted out`,
  ].filter(Boolean);
  return { tone: r.added > 0 ? "green" : "amber", text: `Added ${plural(r.added, "lead")}.${skipped.length ? ` Skipped: ${skipped.join(", ")}.` : ""}` };
}

function aiNotice(done: string, s: { failed: number; rate_limited: boolean; remaining: number; last_error: string | null }): Notice {
  const extras = [
    s.rate_limited && `The AI service asked us to slow down; ${s.remaining} left. Try again in a minute.`,
    s.failed > 0 && `${s.failed} failed${s.last_error ? ` (${s.last_error})` : ""}; they can be retried.`,
  ].filter(Boolean);
  return { tone: s.rate_limited || s.failed > 0 ? "amber" : "green", text: [done, ...extras].join(" ") };
}

export function CampaignWorkspace({
  campaign, initialStats, initialLeads, mailboxes, profileComplete,
}: {
  campaign: Campaign; initialStats: CampaignStats; initialLeads: LeadList; mailboxes: Mailbox[]; profileComplete: boolean;
}) {
  const base = `/campaigns/${campaign.id}`;
  const [stats, setStats] = useState(initialStats);
  const [leads, setLeads] = useState(initialLeads);
  const [drafts, setDrafts] = useState<Draft[] | null>(null);
  const [sent, setSent] = useState<SentEmail[] | null>(null);
  const [tab, setTab] = useState<Tab>("leads");
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice>(null);
  const [showSend, setShowSend] = useState(false);
  const [showSearch, setShowSearch] = useState(false);
  const [minScore, setMinScore] = useState(50);
  const [searchCount, setSearchCount] = useState(20);
  const fileInput = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    const [s, l] = await Promise.all([api<CampaignStats>(`${base}/stats`), api<LeadList>(`${base}/leads?sort=score&limit=200`)]);
    setStats(s);
    setLeads(l);
    setDrafts(null); // stale: reloaded when its tab is open
    setSent(null);
  }, [base]);

  // After approving or editing one draft: update just that draft and the counters, without reloading the list.
  const refreshStats = useCallback(async () => {
    setStats(await api<CampaignStats>(`${base}/stats`));
  }, [base]);

  // Load the drafts / sent lists the first time (or after a change) their tab is showing.
  useEffect(() => {
    let cancelled = false;
    if (tab === "drafts" && drafts === null) {
      api<Draft[]>(`${base}/drafts`).then((d) => !cancelled && setDrafts(d)).catch((e) => !cancelled && setNotice({ tone: "red", text: e.message }));
    }
    if (tab === "sent" && sent === null) {
      api<SentEmail[]>(`${base}/sent`).then((d) => !cancelled && setSent(d)).catch((e) => !cancelled && setNotice({ tone: "red", text: e.message }));
    }
    return () => { cancelled = true; };
  }, [tab, drafts, sent, base]);

  async function run<T>(name: string, fn: () => Promise<T>, done: (r: T) => Notice) {
    setBusy(name);
    setNotice(null);
    try {
      setNotice(done(await fn()));
    } catch (err) {
      const message = err instanceof Error ? err.message : "Something went wrong.";
      setNotice({ tone: "red", text: message.includes("GOOGLE_PLACES_API_KEY") ? "Google Maps search isn't set up yet (no API key). You can still import a CSV." : message });
    } finally {
      await refresh().catch(() => null);
      setBusy(null);
    }
  }

  const importCsv = (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return run("import", () => api<ImportResult>(`${base}/leads/import`, { method: "POST", form }), importNotice);
  };

  // The one step worth doing next gets the dark button; everything else stays quiet.
  const next = nextStep(stats, profileComplete);
  const tone = (key: string) => (next === key ? "primary" : "subtle");

  const steps = [
    {
      key: "leads", title: "1. Leads", value: stats.leads, sub: `${stats.with_email} with an email`,
      action: (
        <div className="flex flex-col gap-1.5">
          <Button variant={tone("leads")} busy={busy === "import"} onClick={() => fileInput.current?.click()}>Import CSV</Button>
          <Button variant="subtle" onClick={() => setShowSearch(true)}>Search Maps</Button>
        </div>
      ),
    },
    {
      key: "enrich", title: "2. Find emails", value: stats.with_email, sub: stats.to_enrich ? `${stats.to_enrich} websites to check` : "nothing to check",
      action: (
        <Button variant={tone("enrich")} disabled={stats.to_enrich === 0} busy={busy === "enrich"}
          onClick={() => run("enrich", () => api<EnrichResult>(`${base}/enrich`, { method: "POST", json: {} }),
            (r) => ({ tone: r.found > 0 ? "green" : "amber", text: `Checked ${plural(r.checked, "website")}: found ${plural(r.found, "email")}.${r.suppressed ? ` ${r.suppressed} were on your opt-out list.` : ""}` }))}>
          Find emails
        </Button>
      ),
    },
    {
      key: "score", title: "3. Score", value: stats.scored, sub: stats.to_score ? `${stats.to_score} to score` : "all scored",
      action: (
        <Button variant={tone("score")} disabled={stats.to_score === 0} busy={busy === "score"}
          onClick={() => run("score", () => api<ScoreSummary>(`${base}/score`, { method: "POST", json: {} }), (r) => aiNotice(`Scored ${plural(r.scored, "lead")}.`, r))}>
          Score leads
        </Button>
      ),
    },
    {
      key: "draft", title: "4. Write emails", value: stats.drafts, sub: stats.to_draft ? `${stats.to_draft} ready to write` : "none waiting",
      action: (
        <div className="space-y-1.5">
          <label className="flex items-center justify-between gap-2 whitespace-nowrap text-xs text-brand-ink/65">
            Min score
            <input type="number" min={0} max={100} value={minScore} onChange={(e) => setMinScore(Math.min(100, Math.max(0, Number(e.target.value) || 0)))}
              className="w-14 rounded-md border border-brand-base/25 px-1.5 py-0.5 text-right text-sm text-brand-ink" />
          </label>
          <Button variant={tone("draft")} className="w-full" disabled={!profileComplete || stats.scored === 0} busy={busy === "draft"}
            title={profileComplete ? undefined : "Complete your sender details in Settings first"}
            onClick={() => run("draft", () => api<DraftSummary>(`${base}/drafts/generate`, { method: "POST", json: { min_score: minScore } }), (r) => aiNotice(`Wrote ${plural(r.generated, "email")}.`, r))}>
            Write emails
          </Button>
        </div>
      ),
    },
    {
      key: "review", title: "5. Review", value: stats.approved, sub: `of ${stats.drafts} approved`,
      action: <Button variant={tone("review")} disabled={stats.drafts === 0} onClick={() => setTab("drafts")}>Review drafts</Button>,
    },
    {
      key: "send", title: "6. Send", value: stats.sent, sub: stats.to_send ? `${stats.to_send} approved, waiting` : "nothing approved",
      action: <Button variant={tone("send")} disabled={stats.to_send === 0} onClick={() => setShowSend(true)}>Send…</Button>,
    },
  ];

  return (
    <div className="space-y-5">
      <input ref={fileInput} type="file" accept=".csv,text/csv" className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) importCsv(f); }} />

      <ol className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-brand-base/10 bg-brand-base/10 md:grid-cols-3 xl:grid-cols-6">
        {steps.map((s) => (
          <li key={s.key} data-next={next === s.key ? "true" : undefined} className="flex flex-col bg-white p-4">
            <div className="flex h-full flex-col">
              <div className="text-xs font-medium text-brand-ink/65">{s.title}</div>
              <div className="mt-1 text-2xl font-medium tabular-nums">{s.value}</div>
              <div className="mb-3 text-xs text-brand-ink/65">{s.sub}</div>
              <div className="mt-auto">{s.action}</div>
            </div>
          </li>
        ))}
      </ol>

      {notice && (
        <div aria-live="polite"><Alert tone={notice.tone}>{notice.text}</Alert></div>
      )}
      {busy && busy !== "import" && (busy === "score" || busy === "draft" || busy === "enrich") && (
        <p className="text-sm text-brand-ink/65">Working on it. This can take a minute for large lists…</p>
      )}

      <div>
        <div role="tablist" className="mb-4 flex flex-wrap gap-1">
          {([["leads", "Leads", leads.total], ["drafts", "Drafts", stats.drafts], ["sent", "Sent", stats.sent]] as const).map(([key, label, count]) => (
            <button key={key} role="tab" aria-selected={tab === key} onClick={() => setTab(key)}
              className={cx("flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors", tab === key ? "border-transparent bg-brand-base/[0.07] text-brand-ink" : "border-transparent text-brand-ink/65 hover:text-brand-ink")}>
              {label}<span className="text-xs tabular-nums text-brand-ink/65">{count}</span>
            </button>
          ))}
        </div>
        {tab === "leads" && <LeadsTable leads={leads.items} total={leads.total} />}
        {tab === "drafts" && (drafts === null ? <p className="text-sm text-brand-ink/65">Loading…</p> : <DraftsPanel drafts={drafts} onChange={(d) => { setDrafts((prev) => prev && prev.map((x) => (x.id === d.id ? d : x))); refreshStats().catch(() => null); }} />)}
        {tab === "sent" && (sent === null ? <p className="text-sm text-brand-ink/65">Loading…</p> : <SentTable rows={sent} />)}
      </div>

      {showSearch && (
        <Modal title="Search Google Maps" onClose={() => setShowSearch(false)}>
          <form className="space-y-4" onSubmit={(e) => {
            e.preventDefault();
            setShowSearch(false);
            run("search", () => api<ImportResult>(`${base}/search`, { method: "POST", json: { max_results: searchCount } }), importNotice);
          }}>
            <p className="text-sm text-brand-ink/75">Finds <strong>{campaign.niche}</strong> businesses in <strong>{campaign.location}</strong> using the official Google Places API.</p>
            <Field label="How many leads" hint="Up to 60.">
              <Input type="number" min={1} max={60} value={searchCount} onChange={(e) => setSearchCount(Math.min(60, Math.max(1, Number(e.target.value) || 1)))} />
            </Field>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="secondary" onClick={() => setShowSearch(false)}>Cancel</Button>
              <Button type="submit">Search</Button>
            </div>
          </form>
        </Modal>
      )}

      {showSend && (
        <SendModal
          campaignId={campaign.id} mailboxes={mailboxes} profileComplete={profileComplete} toSend={stats.to_send}
          onClose={() => setShowSend(false)} onSent={() => { refresh().catch(() => null); }}
        />
      )}
    </div>
  );
}
