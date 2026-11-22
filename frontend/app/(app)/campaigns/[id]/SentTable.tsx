import { Badge, Card, Empty } from "@/components/ui";
import type { SentEmail } from "@/lib/types";

const TONE = { sent: "green", rejected: "red", sending: "amber" } as const;
const LABEL = { sent: "Sent", rejected: "Address refused", sending: "In progress" } as const;

export function SentTable({ rows }: { rows: SentEmail[] }) {
  if (rows.length === 0) {
    return (
      <Card>
        <Empty title="Nothing sent yet">Approved drafts you send will be listed here.</Empty>
      </Card>
    );
  }
  return (
    <Card className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] text-left text-sm">
          <thead className="border-b border-brand-base/15 text-xs font-medium text-brand-ink/65">
            <tr><th className="px-4 py-2 font-medium">To</th><th className="px-4 py-2 font-medium">Subject</th><th className="px-4 py-2 font-medium">Result</th></tr>
          </thead>
          <tbody className="divide-y divide-brand-base/10">
            {rows.map((r) => (
              <tr key={r.id}>
                <td className="px-4 py-3">{r.to_email}</td>
                <td className="px-4 py-3">{r.subject}</td>
                <td className="px-4 py-3">
                  <Badge tone={TONE[r.status as keyof typeof TONE] ?? "gray"} title={r.error ?? undefined}>{LABEL[r.status as keyof typeof LABEL] ?? r.status}</Badge>
                  {r.status === "sending" && <p className="mt-1 text-xs text-amber-700">Never confirmed. Check your mailbox&rsquo;s sent folder before retrying.</p>}
                  {r.error && <p className="mt-1 text-xs text-brand-ink/65">{r.error}</p>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
