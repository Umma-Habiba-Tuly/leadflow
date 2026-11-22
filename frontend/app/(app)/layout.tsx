import Link from "next/link";
import { Alert, LINK, Slash } from "@/components/ui";
import { Mark } from "@/components/Mark";
import { serverApi } from "@/lib/backend";
import type { Campaign, Me } from "@/lib/types";
import { LogoutButton } from "./LogoutButton";
import { NavLinks } from "./NavLinks";
import { Sidebar } from "./Sidebar";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const [me, campaigns] = await Promise.all([serverApi<Me>("/auth/me"), serverApi<Campaign[]>("/campaigns")]);
  return (
    <>
      {/* Like ai-sdk.dev: logo, a slash, the name, links on the left; who you are on the right. No bar, no border. */}
      <header className="flex h-16 items-center justify-between px-6">
        <div className="flex items-center gap-3">
          <Link href="/campaigns" aria-label="LeadFlow home"><Mark size={22} variant="ink" /></Link>
          <div className="hidden items-center gap-3 sm:flex">
            <Slash />
            <Link href="/campaigns" className="text-base font-medium tracking-tight">LeadFlow</Link>
          </div>
          {/* The sidebar has these on wide screens; on small screens they live up here. */}
          <nav aria-label="Primary" className="ml-2 flex items-center gap-4 sm:ml-5 sm:gap-5 lg:hidden">
            <NavLinks />
          </nav>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <span className="hidden text-right leading-tight sm:block">
            <span className="block font-medium">{me.workspace_name}</span>
            <span className="block text-xs text-brand-ink/65">{me.email}</span>
          </span>
          <LogoutButton />
        </div>
      </header>

      <div className="mx-auto flex w-full max-w-[1400px] flex-1 gap-6 px-3 lg:px-4">
        <aside className="hidden w-60 shrink-0 pt-4 lg:block">
          <Sidebar campaigns={campaigns} />
        </aside>
        <main className="min-w-0 flex-1 px-3 pb-20 pt-4 lg:px-6">
          {!me.profile_complete && (
            <div className="mb-6">
              <Alert tone="amber">
                Add your sender details before you can write or send emails: every email must show who it is from and a postal address.{" "}
                <Link href="/settings" className={LINK}>Go to settings</Link>
              </Alert>
            </div>
          )}
          {children}
        </main>
      </div>
    </>
  );
}
