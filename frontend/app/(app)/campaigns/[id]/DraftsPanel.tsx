"use client";

import { useState } from "react";
import { Alert, Badge, Button, Card, Empty, Input, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import type { Draft } from "@/lib/types";

const STATUS = { draft: { label: "Needs review", tone: "amber" }, approved: { label: "Approved", tone: "green" }, sent: { label: "Sent", tone: "blue" } } as const;

function DraftCard({ draft, onChange }: { draft: Draft; onChange: (d: Draft) => void }) {
  const [subject, setSubject] = useState(draft.subject);
  const [body, setBody] = useState(draft.body);
  const [showPreview, setShowPreview] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const dirty = subject !== draft.subject || body !== draft.body;
  const locked = draft.status === "sent";
  const status = STATUS[draft.status as keyof typeof STATUS] ?? { label: draft.status, tone: "gray" as const };

  async function save(name: string, extra: { approved?: boolean }) {
    setBusy(name);
    setError(null);
    try {
      const updated = await api<Draft>(`/drafts/${draft.id}`, {
        method: "PATCH",
        json: { ...(dirty ? { subject, body } : {}), ...extra },
      });
      setSubject(updated.subject);
      setBody(updated.body);
      onChange(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="font-medium">{draft.lead_name}</h3>
          <p className="text-sm text-brand-ink/65">To {draft.to_email}</p>
        </div>
        <Badge tone={status.tone}>{status.label}</Badge>
      </div>

      <div className="mt-3 space-y-3">
        {error && <Alert>{error}</Alert>}
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-brand-ink/65">Subject</span>
          <Input value={subject} onChange={(e) => setSubject(e.target.value)} disabled={locked} maxLength={200} />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-brand-ink/65">Message</span>
          <Textarea value={body} onChange={(e) => setBody(e.target.value)} disabled={locked} rows={7} maxLength={3000} />
        </label>
        {showPreview && (
          <div>
            <p className="mb-1 text-xs font-medium text-brand-ink/65">Exactly what the recipient will receive</p>
            <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded-md border border-brand-base/15 bg-brand-surface p-3 text-xs leading-relaxed">{draft.preview}</pre>
            <p className="mt-1 text-xs text-brand-ink/65">Your name, address and the unsubscribe link are added automatically and cannot be removed.</p>
          </div>
        )}
      </div>

      {!locked && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          {draft.status === "approved" && !dirty ? (
            <Button variant="secondary" busy={busy === "unapprove"} onClick={() => save("unapprove", { approved: false })}>Remove approval</Button>
          ) : (
            <Button busy={busy === "approve"} onClick={() => save("approve", { approved: true })}>{dirty ? "Save & approve" : "Approve"}</Button>
          )}
          {dirty && <Button variant="secondary" busy={busy === "save"} onClick={() => save("save", {})}>Save changes</Button>}
          <Button variant="ghost" onClick={() => setShowPreview((v) => !v)}>{showPreview ? "Hide full email" : "Preview full email"}</Button>
          {dirty && <span className="text-xs text-brand-ink/65">Unsaved edits</span>}
        </div>
      )}
    </Card>
  );
}

export function DraftsPanel({ drafts, onChange }: { drafts: Draft[]; onChange: (d: Draft) => void }) {
  if (drafts.length === 0) {
    return (
      <Card>
        <Empty title="No drafts yet">Score your leads, then choose &ldquo;Write emails&rdquo;. Drafts are written for well-scored leads that have an email address.</Empty>
      </Card>
    );
  }
  const approved = drafts.filter((d) => d.status === "approved").length;
  return (
    <div className="space-y-3">
      <p className="text-sm text-brand-ink/75">
        {drafts.length} drafts, {approved} approved. Read each email before approving. Only approved drafts can be sent.
      </p>
      {drafts.map((d) => (
        <DraftCard key={`${d.id}-${d.status}-${d.subject}-${d.body.length}`} draft={d} onChange={onChange} />
      ))}
    </div>
  );
}
