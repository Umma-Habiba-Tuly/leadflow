import type { Metadata } from "next";
import Link from "next/link";
import { Card, Empty } from "@/components/ui";
import { serverApi } from "@/lib/backend";
import type { Campaign } from "@/lib/types";
import { NewCampaign } from "./NewCampaign";

export const metadata: Metadata = { title: "Campaigns" };

export default async function CampaignsPage() {
  const campaigns = await serverApi<Campaign[]>("/campaigns");
  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl">Campaigns</h1>
          <p className="mt-1 text-brand-ink/65">A campaign is one kind of business in one place, with one thing to offer them.</p>
        </div>
        <NewCampaign />
      </div>

      {campaigns.length === 0 ? (
        <Card>
          <Empty title="No campaigns yet">Create one to start finding leads, for example &ldquo;dental clinics in Austin&rdquo;.</Empty>
        </Card>
      ) : (
        <Card className="overflow-hidden">
          <ul className="divide-y divide-brand-base/10">
            {campaigns.map((c) => (
              <li key={c.id}>
                <Link href={`/campaigns/${c.id}`} className="block px-5 py-4 transition-colors hover:bg-brand-base/[0.03]">
                  <div className="flex items-baseline justify-between gap-4">
                    <h2 className="text-base">{c.name}</h2>
                    <span className="shrink-0 text-sm text-brand-ink/65">{c.niche} · {c.location}</span>
                  </div>
                  {c.offer && <p className="mt-1 line-clamp-1 text-sm text-brand-ink/65">{c.offer}</p>}
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
