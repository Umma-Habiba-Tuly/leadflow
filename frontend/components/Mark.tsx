/**
 * The Circuit Teal mark: an arrow in a rounded square. Per the kit, the fill is Ink, Surface or
 * Accent, and the arrow stroke is Lime (on Ink) or Ink (on Surface / Accent).
 */
const VARIANTS = {
  ink: { fill: "var(--brand-ink)", stroke: "var(--brand-accent)" },
  surface: { fill: "var(--brand-surface)", stroke: "var(--brand-ink)" },
  accent: { fill: "var(--brand-accent)", stroke: "var(--brand-ink)" },
} as const;

export function Mark({ size = 28, variant = "accent", className }: { size?: number; variant?: keyof typeof VARIANTS; className?: string }) {
  const { fill, stroke } = VARIANTS[variant];
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" role="img" aria-label="LeadFlow" className={className}>
      <rect width="32" height="32" rx="8" style={{ fill }} />
      <path d="M10.5 21.5 21.5 10.5M12.5 10.5h9v9" fill="none" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" style={{ stroke }} />
    </svg>
  );
}
