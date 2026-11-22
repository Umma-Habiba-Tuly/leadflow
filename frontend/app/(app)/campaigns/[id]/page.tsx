import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiError, serverApi } from "@/lib/backend";
import type { Campaign, CampaignStats, LeadList, Mailbox, Me } from "@/lib/types";
import { CampaignWorkspace } from "./CampaignWorkspace";

export const metadata: Metadata = { title: "Campaign" };

async function load(id: string) {
  try {
    const [campaign, stats, leads, mailboxes, me] = await Promise.all([
      serverApi<Campaign>(`/campaigns/${id}`),
      serverApi<CampaignStats>(`/campaigns/${id}/stats`),
      serverApi<LeadList>(`/campaigns/${id}/leads?sort=score&limit=200`),
      serverApi<Mailbox[]>("/mailboxes"),
      serverApi<Me>("/auth/me"),
    ]);
    return { campaign, stats, leads, mailboxes, profileComplete: me.profile_complete };
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }
}

export default async function CampaignPage({ params }: PageProps<"/campaigns/[id]">) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) notFound();
  const { campaign, stats, leads, mailboxes, profileComplete } = await load(id);

  return (
    <div className="space-y-5">
      <div>
        <Link href="/campaigns" className="text-sm text-brand-ink/65 hover:text-brand-ink lg:hidden">← All campaigns</Link>
        <h1 className="text-3xl">{campaign.name}</h1>
        <p className="mt-1 text-brand-ink/65">{campaign.niche} · {campaign.location}</p>
        {campaign.offer && <p className="mt-3 max-w-3xl text-sm text-brand-ink/75">Offering: {campaign.offer}</p>}
      </div>
      <CampaignWorkspace campaign={campaign} initialStats={stats} initialLeads={leads} mailboxes={mailboxes} profileComplete={profileComplete} />
    </div>
  );
}
