"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cx } from "@/components/ui";
import type { Campaign } from "@/lib/types";

const item = (active: boolean) =>
  cx("block truncate rounded-lg px-3 py-2 text-sm transition-colors", active ? "bg-brand-base/[0.07] font-medium text-brand-ink" : "text-brand-ink/70 hover:bg-brand-base/5 hover:text-brand-ink");

/** The docs-style left rail: where you are, and every campaign one click away. */
export function Sidebar({ campaigns }: { campaigns: Campaign[] }) {
  const pathname = usePathname();
  const onList = pathname === "/campaigns";
  return (
    <nav aria-label="Main" className="sticky top-4 space-y-6">
      <div>
        <Link href="/campaigns" aria-current={onList ? "page" : undefined} className={item(onList)}>All campaigns</Link>
        {campaigns.length > 0 && (
          <ul className="mt-1 max-h-[55vh] space-y-0.5 overflow-y-auto border-l border-brand-base/12 pl-2 ml-3">
            {campaigns.map((c) => {
              const href = `/campaigns/${c.id}`;
              const active = pathname === href;
              return (
                <li key={c.id}>
                  <Link href={href} aria-current={active ? "page" : undefined} className={item(active)} title={c.name}>{c.name}</Link>
                </li>
              );
            })}
          </ul>
        )}
      </div>
      <Link href="/settings" aria-current={pathname === "/settings" ? "page" : undefined} className={item(pathname === "/settings")}>Settings</Link>
    </nav>
  );
}
