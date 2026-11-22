"use client";

import Link from "next/link";
import { useState } from "react";
import { Alert, Button, Field, Input, Modal, Select } from "@/components/ui";
import { api } from "@/lib/api";
import type { Mailbox, SendSummary } from "@/lib/types";

export function SendModal({
  campaignId, mailboxes, profileComplete, toSend, onClose, onSent,
}: {
  campaignId: number; mailboxes: Mailbox[]; profileComplete: boolean; toSend: number; onClose: () => void; onSent: () => void;
}) {
  const active = mailboxes.filter((m) => m.status === "active");
  const [mailboxId, setMailboxId] = useState<number | null>(active[0]?.id ?? null);
  const [limit, setLimit] = useState(Math.min(10, Math.max(toSend, 1)));
  const [preview, setPreview] = useState<SendSummary | null>(null);
  const [result, setResult] = useState<SendSummary | null>(null);
  const [busy, setBusy] = useState<"preview" | "send" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const mailbox = active.find((m) => m.id === mailboxId) ?? null;

  async function call(dryRun: boolean) {
    if (!mailbox) return;
    setBusy(dryRun ? "preview" : "send");
    setError(null);
    try {
      const summary = await api<SendSummary>(`/campaigns/${campaignId}/send`, {
        method: "POST",
        json: { mailbox_id: mailbox.id, limit, dry_run: dryRun },
      });
      if (dryRun) setPreview(summary);
      else {
        setResult(summary);
        setPreview(null);
        onSent();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setBusy(null);
    }
  }

  const blocked = !profileComplete ? (
    <Alert tone="amber">Add your sender name, company and postal address first. <Link href="/settings" className="font-medium underline">Open settings</Link></Alert>
  ) : active.length === 0 ? (
    <Alert tone="amber">Connect a mailbox to send from. <Link href="/settings" className="font-medium underline">Open settings</Link></Alert>
  ) : null;

  return (
    <Modal title="Send approved emails" onClose={onClose}>
      <div className="space-y-4">
        {blocked}
        {error && <Alert>{error}</Alert>}

        {result ? (
          <div className="space-y-3">
            <Alert tone={result.sent > 0 ? "green" : "amber"}>
              Sent {result.sent} email{result.sent === 1 ? "" : "s"}.
              {result.rejected > 0 && ` ${result.rejected} address${result.rejected === 1 ? " was" : "es were"} refused and won't be tried again.`}
              {result.skipped_opted_out > 0 && ` ${result.skipped_opted_out} skipped because they opted out.`}
            </Alert>
            {result.stopped_reason && <Alert tone="amber">Stopped early: {result.stopped_reason}</Alert>}
            {result.mailbox_paused && <Alert>This mailbox was paused because too many addresses were refused. Check the quality of your list, then reactivate it in settings.</Alert>}
            <div className="flex justify-end"><Button onClick={onClose}>Done</Button></div>
          </div>
        ) : (
          !blocked && (
            <>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Send from">
                  <Select value={mailboxId ?? ""} onChange={(e) => { setMailboxId(Number(e.target.value)); setPreview(null); }}>
                    {active.map((m) => <option key={m.id} value={m.id}>{m.from_email}</option>)}
                  </Select>
                </Field>
                <Field label="How many now" hint={mailbox ? `${mailbox.sent_today} of ${mailbox.daily_limit} used today. Max 20 at a time.` : undefined}>
                  <Input type="number" min={1} max={20} value={limit} onChange={(e) => { setLimit(Math.min(20, Math.max(1, Number(e.target.value) || 1))); setPreview(null); }} />
                </Field>
              </div>

              {!preview ? (
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm text-brand-ink/65">{toSend} approved email{toSend === 1 ? "" : "s"} waiting. Preview first: nothing is sent yet.</p>
                  <Button busy={busy === "preview"} onClick={() => call(true)}>Preview</Button>
                </div>
              ) : (
                <div className="space-y-3">
                  {preview.stopped_reason && <Alert tone="amber">{preview.stopped_reason}</Alert>}
                  {preview.skipped_opted_out > 0 && <Alert tone="amber">{preview.skipped_opted_out} will be skipped because they opted out.</Alert>}
                  {preview.would_send.length === 0 ? (
                    <p className="text-sm text-brand-ink/75">Nothing would be sent.</p>
                  ) : (
                    <>
                      <p className="text-sm font-medium">These {preview.would_send.length} emails would be sent:</p>
                      <ul className="max-h-56 divide-y divide-brand-base/10 overflow-y-auto rounded-md border border-brand-base/15 text-sm">
                        {preview.would_send.map((w) => (
                          <li key={w.draft_id} className="px-3 py-2"><span className="font-medium">{w.to_email}</span><span className="block text-xs text-brand-ink/65">{w.subject}</span></li>
                        ))}
                      </ul>
                    </>
                  )}
                  <div className="flex items-center justify-between gap-3 border-t border-brand-base/10 pt-3">
                    <p className="text-xs text-brand-ink/65">Real emails cannot be unsent.</p>
                    <div className="flex gap-2">
                      <Button variant="secondary" onClick={() => setPreview(null)}>Back</Button>
                      <Button variant="danger" busy={busy === "send"} disabled={preview.would_send.length === 0} onClick={() => call(false)}>
                        Send {preview.would_send.length} email{preview.would_send.length === 1 ? "" : "s"} now
                      </Button>
                    </div>
                  </div>
                </div>
              )}
            </>
          )
        )}
      </div>
    </Modal>
  );
}
