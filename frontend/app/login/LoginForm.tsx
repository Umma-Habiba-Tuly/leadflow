"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Alert, Button, Field, Input, LINK } from "@/components/ui";

export function LoginForm({ initialMode = "signin" }: { initialMode?: "signin" | "register" }) {
  const router = useRouter();
  const [mode, setMode] = useState<"signin" | "register">(initialMode);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [company, setCompany] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(mode === "signin" ? "/api/auth/login" : "/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(mode === "signin" ? { email, password } : { email, password, workspace_name: company }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        setError(typeof data?.detail === "string" ? data.detail : "Something went wrong. Please try again.");
        return;
      }
      router.replace("/campaigns");
      router.refresh();
    } catch {
      setError("Cannot reach the server. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="w-full max-w-sm">
      <div className="text-center">
        <h1 className="text-4xl leading-[1.1]">{mode === "signin" ? "Sign in to LeadFlow" : "Create your account"}</h1>
        <p className="mt-3 text-base text-brand-ink/65">Find leads, score them, and send compliant outreach.</p>
      </div>

      <form onSubmit={submit} className="mt-10 space-y-4">
        {error && <Alert>{error}</Alert>}
        {mode === "register" && (
          <Field label="Company name" hint="Your workspace. Each company's data is kept separate.">
            <Input value={company} onChange={(e) => setCompany(e.target.value)} required maxLength={200} autoComplete="organization" />
          </Field>
        )}
        <Field label="Email">
          <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
        </Field>
        <Field label="Password" hint={mode === "register" ? "At least 8 characters." : undefined}>
          <Input
            type="password" value={password} onChange={(e) => setPassword(e.target.value)} required
            minLength={mode === "register" ? 8 : undefined} autoComplete={mode === "signin" ? "current-password" : "new-password"}
          />
        </Field>
        <Button type="submit" busy={busy} className="w-full py-2.5">{mode === "signin" ? "Sign in" : "Create account"}</Button>
      </form>
      <p className="mt-6 text-center text-sm text-brand-ink/65">
        {mode === "signin" ? "New here? " : "Already have an account? "}
        <button type="button" className={`font-medium ${LINK}`} onClick={() => { setMode(mode === "signin" ? "register" : "signin"); setError(null); }}>
          {mode === "signin" ? "Create an account" : "Sign in"}
        </button>
      </p>
    </div>
  );
}
