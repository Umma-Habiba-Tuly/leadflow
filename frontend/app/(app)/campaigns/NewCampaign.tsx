"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Alert, Button, Field, Input, Modal, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import type { Campaign } from "@/lib/types";

export function NewCampaign() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      const created = await api<Campaign>("/campaigns", {
        method: "POST",
        json: { name: f.get("name"), niche: f.get("niche"), location: f.get("location"), offer: (f.get("offer") as string) || null },
      });
      router.refresh(); // the sidebar's campaign list is rendered by the layout, which a client navigation would not re-run
      router.push(`/campaigns/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the campaign.");
      setBusy(false);
    }
  }

  return (
    <>
      <Button onClick={() => setOpen(true)}>New campaign</Button>
      {open && (
        <Modal title="New campaign" onClose={() => setOpen(false)}>
          <form onSubmit={submit} className="space-y-4">
            {error && <Alert>{error}</Alert>}
            <Field label="Campaign name"><Input name="name" required maxLength={200} placeholder="Austin dentists" /></Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Kind of business"><Input name="niche" required maxLength={200} placeholder="dental clinic" /></Field>
              <Field label="Where"><Input name="location" required maxLength={200} placeholder="Austin, TX" /></Field>
            </div>
            <Field label="What are you offering them?" hint="The AI uses this to judge which leads are a good fit and to write the emails. Be specific.">
              <Textarea name="offer" rows={3} maxLength={1000} placeholder="Website redesign and local SEO for dental clinics that want more new-patient bookings" />
            </Field>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
              <Button type="submit" busy={busy}>Create campaign</Button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
