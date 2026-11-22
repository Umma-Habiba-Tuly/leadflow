"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Alert, Badge, Button, Card, Empty, Field, Input, Select } from "@/components/ui";
import { api } from "@/lib/api";
import type { Mailbox, Profile, Suppression } from "@/lib/types";

function Section({ title, description, children }: { title: string; description: string; children: React.ReactNode }) {
  return (
    <section className="grid gap-4 lg:grid-cols-[18rem_1fr]">
      <div>
        <h2 className="font-medium">{title}</h2>
        <p className="mt-1 text-sm text-brand-ink/65">{description}</p>
      </div>
      <div>{children}</div>
    </section>
  );
}

const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Something went wrong.");

// ---------- sender profile ----------

function ProfileForm({ initial }: { initial: Profile }) {
  const router = useRouter();
  const [profile, setProfile] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: "green" | "red"; text: string } | null>(null);

  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setMsg(null);
    try {
      const saved = await api<Profile>("/workspace/profile", {
        method: "PUT",
        json: { sender_name: f.get("sender_name"), company_name: f.get("company_name"), postal_address: f.get("postal_address") },
      });
      setProfile(saved);
      setMsg({ tone: "green", text: saved.complete ? "Saved. You can now write and send emails." : "Saved, but some details are still missing." });
      router.refresh();
    } catch (err) {
      setMsg({ tone: "red", text: errMsg(err) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="p-5">
      <form onSubmit={save} className="space-y-4">
        {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}
        {!profile.complete && !msg && <Alert tone="amber">Missing: {profile.missing.map((m) => m.replace("_", " ")).join(", ")}.</Alert>}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Your name"><Input name="sender_name" defaultValue={profile.sender_name ?? ""} required maxLength={200} placeholder="Sam Rivera" /></Field>
          <Field label="Company"><Input name="company_name" defaultValue={profile.company_name ?? ""} required maxLength={200} placeholder="Rivera Web Studio" /></Field>
        </div>
        <Field label="Postal address" hint="Required by anti-spam law (CAN-SPAM) on every commercial email.">
          <Input name="postal_address" defaultValue={profile.postal_address ?? ""} required maxLength={500} placeholder="100 Congress Ave, Austin, TX 78701" />
        </Field>
        <div className="flex justify-end"><Button type="submit" busy={busy}>Save</Button></div>
      </form>
    </Card>
  );
}

// ---------- mailboxes ----------

function MailboxRow({ mailbox, onChange }: { mailbox: Mailbox; onChange: (m: Mailbox) => void }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [limit, setLimit] = useState(mailbox.daily_limit);
  const [msg, setMsg] = useState<{ tone: "green" | "red"; text: string } | null>(null);

  async function patch(name: string, json: object) {
    setBusy(name);
    setMsg(null);
    try {
      onChange(await api<Mailbox>(`/mailboxes/${mailbox.id}`, { method: "PATCH", json }));
    } catch (err) {
      setMsg({ tone: "red", text: errMsg(err) });
    } finally {
      setBusy(null);
    }
  }

  async function test() {
    setBusy("test");
    setMsg(null);
    try {
      await api(`/mailboxes/${mailbox.id}/check`, { method: "POST" });
      setMsg({ tone: "green", text: "Connected and signed in. Nothing was sent." });
    } catch (err) {
      setMsg({ tone: "red", text: errMsg(err) });
    } finally {
      setBusy(null);
    }
  }

  const paused = mailbox.status !== "active";
  return (
    <li className="space-y-3 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="font-medium">{mailbox.from_email}</div>
          <div className="text-xs text-brand-ink/65">{mailbox.smtp_host}:{mailbox.smtp_port} · {mailbox.security}</div>
        </div>
        <Badge tone={paused ? "red" : "green"}>{paused ? "Paused" : "Active"}</Badge>
      </div>
      {mailbox.paused_reason && <Alert tone="amber">{mailbox.paused_reason}</Alert>}
      {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-xs text-brand-ink/65">
          Daily limit ({mailbox.sent_today} used today)
          <span className="mt-1 flex gap-2">
            <input type="number" min={1} max={200} value={limit} onChange={(e) => setLimit(Number(e.target.value))}
              className="w-20 rounded-md border border-brand-base/25 px-2 py-1 text-sm text-brand-ink" />
            <Button variant="secondary" disabled={limit === mailbox.daily_limit || limit < 1 || limit > 200} busy={busy === "limit"} onClick={() => patch("limit", { daily_limit: limit })}>Save</Button>
          </span>
        </label>
        <Button variant="secondary" busy={busy === "test"} onClick={test}>Test connection</Button>
        <Button variant="ghost" busy={busy === "status"} onClick={() => patch("status", { status: paused ? "active" : "paused" })}>{paused ? "Reactivate" : "Pause"}</Button>
      </div>
    </li>
  );
}

function Mailboxes({ initial }: { initial: Mailbox[] }) {
  const [mailboxes, setMailboxes] = useState(initial);
  const [adding, setAdding] = useState(initial.length === 0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function add(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    setBusy(true);
    setError(null);
    try {
      const created = await api<Mailbox>("/mailboxes", {
        method: "POST",
        json: {
          from_email: f.get("from_email"), from_name: (f.get("from_name") as string) || null, smtp_host: f.get("smtp_host"),
          smtp_port: Number(f.get("smtp_port")), security: f.get("security"), smtp_username: f.get("smtp_username"),
          smtp_password: f.get("smtp_password"), daily_limit: Number(f.get("daily_limit")),
        },
      });
      setMailboxes((m) => [...m, created]);
      setAdding(false);
      form.reset();
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <Alert tone="blue">
        Send from your <strong>own</strong> business mailbox (Google Workspace, Microsoft 365 or similar), not a bulk-email service.
        Start small: about 20 to 30 emails a day. Gmail needs an app password.
      </Alert>
      <Card>
        {mailboxes.length === 0 ? (
          <Empty title="No mailbox connected">Connect one to send your approved emails.</Empty>
        ) : (
          <ul className="divide-y divide-brand-base/10">
            {mailboxes.map((m) => (
              <MailboxRow key={m.id} mailbox={m} onChange={(u) => setMailboxes((all) => all.map((x) => (x.id === u.id ? u : x)))} />
            ))}
          </ul>
        )}
      </Card>

      {adding ? (
        <Card className="p-5">
          <form onSubmit={add} className="space-y-4">
            <h3 className="font-medium">Connect a mailbox</h3>
            {error && <Alert>{error}</Alert>}
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="From email"><Input name="from_email" type="email" required placeholder="sam@yourcompany.com" /></Field>
              <Field label="From name (optional)"><Input name="from_name" maxLength={200} placeholder="Sam Rivera" /></Field>
              <Field label="SMTP server"><Input name="smtp_host" required placeholder="smtp.gmail.com" /></Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Port"><Input name="smtp_port" type="number" min={1} max={65535} defaultValue={587} required /></Field>
                <Field label="Security">
                  <Select name="security" defaultValue="starttls">
                    <option value="starttls">STARTTLS (587)</option>
                    <option value="ssl">SSL (465)</option>
                    <option value="none">None (local testing only)</option>
                  </Select>
                </Field>
              </div>
              <Field label="Username"><Input name="smtp_username" required autoComplete="off" /></Field>
              <Field label="Password" hint="Stored encrypted. Never shown again."><Input name="smtp_password" type="password" required autoComplete="new-password" /></Field>
              <Field label="Daily limit"><Input name="daily_limit" type="number" min={1} max={200} defaultValue={30} required /></Field>
            </div>
            <div className="flex justify-end gap-2">
              {mailboxes.length > 0 && <Button type="button" variant="secondary" onClick={() => setAdding(false)}>Cancel</Button>}
              <Button type="submit" busy={busy}>Connect mailbox</Button>
            </div>
          </form>
        </Card>
      ) : (
        <Button variant="secondary" onClick={() => setAdding(true)}>Connect another mailbox</Button>
      )}
    </div>
  );
}

// ---------- opt-outs ----------

function OptOuts({ initial }: { initial: Suppression[] }) {
  const [list, setList] = useState(initial);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await api<Suppression>("/suppressions", { method: "POST", json: { email, reason: "added manually" } });
      setList((l) => (l.some((x) => x.id === created.id) ? l : [...l, created]));
      setEmail("");
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <Card>
        {list.length === 0 ? (
          <Empty title="Nobody has opted out yet">People who click &ldquo;unsubscribe&rdquo;, and addresses that bounce, appear here. They are never emailed again.</Empty>
        ) : (
          <ul className="max-h-72 divide-y divide-brand-base/10 overflow-y-auto text-sm">
            {list.map((s) => (
              <li key={s.id} className="flex items-center justify-between gap-3 px-4 py-2.5">
                <span>{s.email}</span>
                <Badge>{s.reason.replace("_", " ")}</Badge>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <form onSubmit={add} className="flex flex-wrap items-end gap-2">
        <div className="min-w-60 flex-1">
          <Field label="Never contact this address">
            <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required placeholder="someone@example.com" />
          </Field>
        </div>
        <Button type="submit" variant="secondary" busy={busy}>Add</Button>
      </form>
      {error && <Alert>{error}</Alert>}
    </div>
  );
}

export function SettingsClient({
  initialProfile, initialMailboxes, initialSuppressions,
}: { initialProfile: Profile; initialMailboxes: Mailbox[]; initialSuppressions: Suppression[] }) {
  return (
    <div className="space-y-10">
      <Section title="Sender details" description="Printed on every email. Anti-spam law requires a real sender identity and postal address.">
        <ProfileForm initial={initialProfile} />
      </Section>
      <Section title="Mailboxes" description="Emails go out from your own mailbox, a limited number per day, so your domain's reputation stays yours.">
        <Mailboxes initial={initialMailboxes} />
      </Section>
      <Section title="Do not contact" description="Everyone here is skipped, always. Unsubscribe links add people automatically.">
        <OptOuts initial={initialSuppressions} />
      </Section>
    </div>
  );
}
