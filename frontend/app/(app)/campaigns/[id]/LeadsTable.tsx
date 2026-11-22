import { Badge, Card, Empty, LINK, type Tone } from "@/components/ui";
import type { Lead } from "@/lib/types";
import { scoreTone } from "@/lib/score";
import { hostOf, safeHttpUrl } from "@/lib/url";

const STATUS: Record<string, { label: string; tone: Tone }> = {
  new: { label: "New", tone: "gray" },
  contacted: { label: "Contacted", tone: "blue" },
  do_not_contact: { label: "Opted out", tone: "red" },
};

export function LeadsTable({ leads, total }: { leads: Lead[]; total: number }) {
  if (leads.length === 0) {
    return (
      <Card>
        <Empty title="No leads yet">Import a CSV or search Google Maps above. Leads with no email can have one found from their website.</Empty>
      </Card>
    );
  }
  return (
    <Card className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead className="border-b border-brand-base/15 text-xs font-medium text-brand-ink/65">
            <tr>
              <th className="px-4 py-2 font-medium">Lead</th>
              <th className="px-4 py-2 font-medium">Score</th>
              <th className="px-4 py-2 font-medium">Email</th>
              <th className="px-4 py-2 font-medium">Website</th>
              <th className="px-4 py-2 font-medium">Rating</th>
              <th className="px-4 py-2 font-medium">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-brand-base/10">
            {leads.map((lead) => {
              const site = safeHttpUrl(lead.website);
              const status = STATUS[lead.status] ?? { label: lead.status, tone: "gray" as Tone };
              return (
                <tr key={lead.id} className="align-top">
                  <td className="max-w-xs px-4 py-3">
                    <div className="font-medium">{lead.name}</div>
                    {lead.score_reason && <div className="mt-0.5 line-clamp-2 text-xs text-brand-ink/65">{lead.score_reason}</div>}
                  </td>
                  <td className="px-4 py-3">
                    {lead.score === null ? <span className="text-brand-ink/65">Not scored</span> : <Badge tone={scoreTone(lead.score)}>{lead.score}</Badge>}
                  </td>
                  <td className="px-4 py-3">{lead.email ?? <span className="text-brand-ink/65">None found</span>}</td>
                  <td className="px-4 py-3">
                    {site ? (
                      <a href={site} target="_blank" rel="noopener noreferrer" className={LINK}>{hostOf(site)}</a>
                    ) : lead.website ? (
                      <span className="text-brand-ink/65" title="Not a valid web address">{lead.website}</span>
                    ) : (
                      <span className="text-brand-ink/65">None</span>
                    )}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    {lead.rating !== null ? `${lead.rating.toFixed(1)} ★${lead.review_count !== null ? ` (${lead.review_count})` : ""}` : <span className="text-brand-ink/65">n/a</span>}
                  </td>
                  <td className="px-4 py-3"><Badge tone={status.tone}>{status.label}</Badge></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {total > leads.length && <p className="border-t border-brand-base/10 px-4 py-2 text-xs text-brand-ink/65">Showing the top {leads.length} of {total} leads.</p>}
    </Card>
  );
}
