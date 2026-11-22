import Link from "next/link";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

/*
 * Plain on purpose: near-white page, white cards, 1px borders, one near-black primary button, no shadows,
 * no gradients. Circuit Teal shows up in a few quiet places (contrast checked in tests/brand.test.ts):
 *   - Ink (near-black) is the primary button, with Surface text.
 *   - Lime appears only in the logo mark.
 *   - Signal Teal is for non-text only: focus rings and link underlines. (Surface on Primary is 4.26:1,
 *     fine for large bold text only, so small text never sits on it.)
 */

export function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

type Variant = "primary" | "secondary" | "subtle" | "danger" | "ghost";
const VARIANTS: Record<Variant, string> = {
  primary: "bg-brand-ink text-brand-surface hover:bg-brand-base disabled:opacity-40",
  secondary: "border border-brand-base/20 bg-white text-brand-ink hover:bg-brand-surface disabled:text-brand-ink/40 disabled:hover:bg-white",
  danger: "bg-rose-700 text-white hover:bg-rose-800 disabled:opacity-40",
  subtle: "bg-brand-base/[0.06] text-brand-ink hover:bg-brand-base/10 disabled:bg-transparent disabled:text-brand-ink/40",
  ghost: "text-brand-ink/70 hover:bg-brand-base/5 hover:text-brand-ink disabled:text-brand-ink/35",
};

export function buttonClasses(variant: Variant = "primary", className?: string) {
  return cx(
    "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-lg px-3.5 py-2 text-sm font-medium transition-colors",
    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-primary disabled:cursor-not-allowed",
    VARIANTS[variant], className,
  );
}

/** A link that looks like a button. */
export function LinkButton({ href, variant = "primary", className, children }: { href: string; variant?: Variant; className?: string; children: ReactNode }) {
  return <Link href={href} className={buttonClasses(variant, className)}>{children}</Link>;
}

export function Button({
  variant = "primary", busy, className, children, disabled, ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; busy?: boolean }) {
  return (
    <button
      {...rest}
      disabled={disabled || busy}
      className={buttonClasses(variant, className)}
    >
      {busy && <span aria-hidden className="size-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />}
      {children}
    </button>
  );
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx("rounded-xl border border-brand-base/10 bg-white", className)}>{children}</div>;
}

const TONES = {
  green: "bg-brand-primary/10 text-brand-base",
  amber: "bg-amber-50 text-amber-900",
  gray: "bg-brand-base/[0.06] text-brand-ink/75",
  red: "bg-rose-50 text-rose-800",
  blue: "bg-brand-base/[0.06] text-brand-base",
} as const;
export type Tone = keyof typeof TONES;

export function Badge({ tone = "gray", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return (
    <span title={title} className={cx("inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium", TONES[tone])}>
      {children}
    </span>
  );
}

export function Alert({ tone = "red", children }: { tone?: "red" | "green" | "amber" | "blue"; children: ReactNode }) {
  const styles = {
    red: "border-rose-200 bg-rose-50 text-rose-900",
    green: "border-transparent bg-transparent px-0 text-brand-ink/75",
    amber: "border-amber-200 bg-amber-50 text-amber-950",
    blue: "border-transparent bg-transparent px-0 text-brand-ink/75",
  }[tone];
  return (
    <div role={tone === "red" ? "alert" : "status"} className={cx("rounded-lg border px-3 py-2 text-sm", styles)}>
      {children}
    </div>
  );
}

/** Links in running text: Deep Teal text (14.5:1) with a Signal Teal underline. */
export const LINK = "text-brand-base underline decoration-brand-primary decoration-1 underline-offset-2 hover:decoration-2";

const FIELD =
  "block w-full rounded-lg border border-brand-base/20 bg-white px-3 py-2 text-sm placeholder:text-brand-ink/65 " +
  "focus:border-brand-ink focus:outline-none focus:ring-2 focus:ring-brand-primary/30 disabled:bg-brand-page";

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-brand-ink/65">{hint}</span>}
    </label>
  );
}
export const Input = (p: InputHTMLAttributes<HTMLInputElement>) => <input {...p} className={cx(FIELD, p.className)} />;
export const Textarea = (p: TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea {...p} className={cx(FIELD, p.className)} />;
export const Select = (p: SelectHTMLAttributes<HTMLSelectElement>) => <select {...p} className={cx(FIELD, p.className)} />;

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-brand-ink/40 p-4 pt-16" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div role="dialog" aria-modal="true" aria-label={title} className="w-full max-w-2xl rounded-xl border border-brand-base/10 bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-brand-base/10 px-5 py-3">
          <h2 className="text-base">{title}</h2>
          <button onClick={onClose} aria-label="Close" className="rounded p-1 text-brand-ink/65 hover:bg-brand-base/5 focus-visible:outline-2 focus-visible:outline-brand-primary">✕</button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

/** The "/" between logo and name, as on ai-sdk.dev. Pure decoration: hidden from assistive tech, so exempt from the text contrast rule. */
export function Slash() {
  return <span aria-hidden className="text-lg text-brand-ink/25">/</span>;
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="px-6 py-12 text-center">
      <p className="text-sm font-medium">{title}</p>
      {children && <div className="mx-auto mt-1 max-w-md text-sm text-brand-ink/65">{children}</div>}
    </div>
  );
}
