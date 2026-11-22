import type { Metadata } from "next";
import { serverApi } from "@/lib/backend";
import type { Mailbox, Profile, Suppression } from "@/lib/types";
import { SettingsClient } from "./SettingsClient";

export const metadata: Metadata = { title: "Settings" };

export default async function SettingsPage() {
  const [profile, mailboxes, suppressions] = await Promise.all([
    serverApi<Profile>("/workspace/profile"),
    serverApi<Mailbox[]>("/mailboxes"),
    serverApi<Suppression[]>("/suppressions"),
  ]);
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-xl font-medium">Settings</h1>
        <p className="text-sm text-brand-ink/65">Who your emails come from, where they are sent from, and who must never be contacted.</p>
      </div>
      <SettingsClient initialProfile={profile} initialMailboxes={mailboxes} initialSuppressions={suppressions} />
    </div>
  );
}
