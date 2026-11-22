import type { Metadata } from "next";
import Link from "next/link";
import { Mark } from "@/components/Mark";
import { Slash } from "@/components/ui";
import { LoginForm } from "./LoginForm";

export const metadata: Metadata = { title: "Sign in" };

export default async function LoginPage({ searchParams }: PageProps<"/login">) {
  const { mode } = await searchParams;
  return (
    <main className="flex flex-1 flex-col">
      {/* Same header as the app, as on ai-sdk.dev: logo, slash, name. The content below is centred. */}
      <header className="flex h-16 items-center gap-3 px-6">
        <Link href="/login" aria-label="LeadFlow"><Mark size={22} variant="ink" /></Link>
        <Slash />
        <span className="text-base font-medium tracking-tight">LeadFlow</span>
      </header>
      <div className="flex flex-1 items-center justify-center px-4 pb-24 pt-8">
        <LoginForm initialMode={mode === "register" ? "register" : "signin"} />
      </div>
    </main>
  );
}
