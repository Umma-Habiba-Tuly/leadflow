"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cx } from "@/components/ui";

const LINKS = [
  ["Campaigns", "/campaigns"],
  ["Settings", "/settings"],
] as const;

export function NavLinks() {
  const pathname = usePathname();
  return (
    <>
      {LINKS.map(([label, href]) => {
        const active = pathname === href || pathname.startsWith(`${href}/`);
        return (
          <Link key={href} href={href} aria-current={active ? "page" : undefined}
            className={cx("text-sm transition-colors", active ? "font-medium text-brand-ink" : "text-brand-ink/65 hover:text-brand-ink")}>
            {label}
          </Link>
        );
      })}
    </>
  );
}
