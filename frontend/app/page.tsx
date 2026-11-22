import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { Mark } from "@/components/Mark";
import { LinkButton, Slash } from "@/components/ui";
import { HowItWorks } from "@/components/landing/HowItWorks";
import { getToken } from "@/lib/session";

export const metadata: Metadata = {
  title: { absolute: "LeadFlow: find leads, score them, send emails you've approved" },
  description: "LeadFlow finds businesses worth contacting, ranks them against your offer, and drafts each email for you to review.",
};

const SAFEGUARDS = [
  ["Opt-outs, always", "Every email carries an unsubscribe link. Anyone who clicks it is never emailed again, and the list is checked once more just before each send."],
  ["You stay in the loop", "Drafts are approved one at a time. Sending is previewed first, and each mailbox has a daily limit."],
  ["Your own mailbox", "Emails go out from your own business address, so your domain's reputation stays yours and replies reach your inbox."],
] as const;

export default async function Landing() {
  if (await getToken()) redirect("/campaigns"); // already signed in: straight to the app

  return (
    <div className="flex flex-1 flex-col">
      <header className="flex h-16 items-center justify-between px-6">
        <div className="flex items-center gap-3">
          <Link href="/" aria-label="LeadFlow home"><Mark size={22} variant="ink" /></Link>
          <div className="hidden items-center gap-3 sm:flex">
            <Slash />
            <span className="text-base font-medium tracking-tight">LeadFlow</span>
          </div>
          <a href="#how" className="ml-5 hidden text-sm text-brand-ink/65 hover:text-brand-ink md:block">How it works</a>
        </div>
        <div className="flex items-center gap-2">
          <LinkButton href="/login" variant="ghost">Sign in</LinkButton>
          <LinkButton href="/login?mode=register">Get started</LinkButton>
        </div>
      </header>

      <main className="flex-1">
        <section className="mx-auto max-w-5xl px-4 pb-16 pt-20 text-center sm:pt-28">
          <h1 className="text-[2.5rem] leading-[1.06] tracking-[-0.045em] sm:text-6xl">
            {/* One sentence per line, so "Score" is never separated from "them." */}
            <span className="block">Find leads. Score them.</span>{" "}
            <span className="block">Send emails you&rsquo;ve approved.</span>
          </h1>
          <p className="mx-auto mt-7 max-w-2xl text-lg leading-relaxed text-brand-ink/65">
            LeadFlow finds businesses worth contacting, ranks them against what you offer, and drafts each email for you to review. Sender details and opt-outs are built in.
          </p>
          <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
            <LinkButton href="/login?mode=register" className="px-5 py-2.5">Get started</LinkButton>
          </div>
        </section>

        <section className="px-4 pb-20">
          <HowItWorks />
        </section>

        <section className="mx-auto max-w-5xl px-4 pb-24">
          <h2 className="text-center text-3xl sm:text-4xl">Built to be safe to send</h2>
          <div className="mt-10 grid gap-8 text-center sm:grid-cols-3 sm:text-left">
            {SAFEGUARDS.map(([title, text]) => (
              <div key={title}>
                <h3 className="text-lg">{title}</h3>
                <p className="mt-2 text-brand-ink/65">{text}</p>
              </div>
            ))}
          </div>
        </section>
      </main>

      <footer className="px-6 py-8 text-sm text-brand-ink/65">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
          <span>LeadFlow</span>
          <Link href="/login" className="hover:text-brand-ink">Sign in</Link>
        </div>
      </footer>
    </div>
  );
}
