import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";

/**
 * Circuit Teal brand kit v1 is LOCKED, and the kit publishes safe/avoid pairings but not
 * contrast numbers. These tests make the numbers explicit so a later edit can't quietly
 * break the kit's rules or accessibility.
 */
const ROOT = path.resolve(import.meta.dirname, "..");
const css = fs.readFileSync(path.join(ROOT, "app/globals.css"), "utf8");

const KIT = { base: "#0E2E2B", primary: "#10847E", accent: "#B7E85A", surface: "#EFFAF6", ink: "#10201D" } as const;
const WHITE = "#FFFFFF";

const rgb = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const linear = (c: number) => ((c /= 255) <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const luminance = (hex: string) => {
  const [r, g, b] = rgb(hex).map(linear);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const contrast = (a: string, b: string) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};
/** A foreground at partial opacity over a background, as the browser would paint it. */
const blend = (fg: string, bg: string, alpha: number) => {
  const mixed = rgb(fg).map((c, i) => Math.round(alpha * c + (1 - alpha) * rgb(bg)[i]));
  return "#" + mixed.map((c) => c.toString(16).padStart(2, "0")).join("");
};

/** The page background: Surface lightened 55% toward white. Derived from a kit token, not a new colour. */
const PAGE = blend(WHITE, KIT.surface, 0.55);
/** Soft tint used behind "positive" badges: Signal Teal at 10% over white. */
const TINT = blend(KIT.primary, WHITE, 0.10);

function sourceFiles(dir: string): string[] {
  return fs.readdirSync(path.join(ROOT, dir), { withFileTypes: true }).flatMap((e) => {
    const rel = path.join(dir, e.name);
    if (e.isDirectory()) return sourceFiles(rel);
    return /\.(tsx|css)$/.test(e.name) ? [rel] : [];
  });
}
const SOURCES = [...sourceFiles("app"), ...sourceFiles("components")].map((f) => ({ file: f, text: fs.readFileSync(path.join(ROOT, f), "utf8") }));

describe("the five brand tokens are exactly the kit's", () => {
  it.each(Object.entries(KIT))("--brand-%s", (name, hex) => {
    const match = css.match(new RegExp(`--brand-${name}:\\s*(#[0-9A-Fa-f]{6})`));
    expect(match?.[1].toUpperCase()).toBe(hex);
  });
});

describe("the derived page background", () => {
  it("is exactly Surface lightened 55% toward white, declared once in globals.css", () => {
    expect(css).toMatch(/--brand-page:\s*color-mix\(in srgb,\s*white 55%,\s*var\(--brand-surface\)\)/);
    expect(PAGE).toBe("#f8fdfb");
  });
});

describe("contrast of the pairings the UI actually uses (WCAG AA: 4.5 for text)", () => {
  const AA = 4.5;
  it.each([
    ["Ink on Surface (kit: safe)", KIT.ink, KIT.surface],
    ["Surface on Base (kit: safe)", KIT.surface, KIT.base],
    ["Ink on Accent (kit: safe CTA)", KIT.ink, KIT.accent],
    ["Ink on white cards", KIT.ink, WHITE],
    ["Lime on Deep Teal (score tag)", KIT.accent, KIT.base],
    ["Deep Teal links on white", KIT.base, WHITE],
    ["Ink on the page background", KIT.ink, PAGE],
    ["Deep Teal links on the page background", KIT.base, PAGE],
    ["Surface on Ink (primary button)", KIT.surface, KIT.ink],
    ["Surface on Deep Teal (primary button hover)", KIT.surface, KIT.base],
    ["Deep Teal on the soft teal badge tint", KIT.base, TINT],
    ["Deep Teal text on Surface", KIT.base, KIT.surface],
  ])("%s", (_label, fg, bg) => {
    expect(contrast(fg, bg)).toBeGreaterThanOrEqual(AA);
  });

  it("the kit's own 'Surface on Primary' is only large-text safe, so the UI must not use it for small text", () => {
    const ratio = contrast(KIT.surface, KIT.primary);
    expect(ratio).toBeGreaterThanOrEqual(3);
    expect(ratio).toBeLessThan(AA); // documents why buttons are Ink-on-Lime instead
  });

  it("the kit's 'avoid' pairings really are poor, as the kit says", () => {
    expect(contrast(KIT.accent, KIT.surface)).toBeLessThan(3);
    expect(contrast(KIT.primary, KIT.base)).toBeLessThan(4.5);
  });
});

describe("muted text stays readable", () => {
  // Text that is aria-hidden is pure decoration (WCAG exempts it); everything else must be readable.
  const used = (re: RegExp) =>
    [...new Set(SOURCES.flatMap((s) => s.text.split("\n").filter((line) => !line.includes("aria-hidden")).flatMap((line) => [...line.matchAll(re)].map((m) => Number(m[1])))))];

  it("every text-brand-ink/NN on a light surface is at least AA", () => {
    const levels = used(/(?<![:\w-])text-brand-ink\/(\d+)/g); // plain (not disabled:/hover:) variants
    expect(levels.length).toBeGreaterThan(0);
    for (const n of levels) {
      for (const bg of [WHITE, KIT.surface, PAGE]) {
        expect(contrast(blend(KIT.ink, bg, n / 100), bg), `ink/${n} on ${bg}`).toBeGreaterThanOrEqual(4.5);
      }
    }
  });

  it("every text-brand-surface/NN on the dark header is at least AA", () => {
    for (const n of used(/(?<![:\w-])text-brand-surface\/(\d+)/g)) {
      expect(contrast(blend(KIT.surface, KIT.base, n / 100), KIT.base), `surface/${n} on base`).toBeGreaterThanOrEqual(4.5);
    }
  });
});

describe("source obeys the kit's rules", () => {
  const offenders = (re: RegExp) => SOURCES.filter((s) => re.test(s.text)).map((s) => s.file);

  it("no leftover generic palette (indigo/slate) that would drift from the brand", () => {
    expect(offenders(/\b(indigo|slate)-\d{2,3}\b/)).toEqual([]);
  });
  it("Lime is for the logo mark only: never as text (the kit's 'avoid' pairing) and never as a UI background class", () => {
    expect(offenders(/(?<![:\w-])text-brand-accent/)).toEqual([]);
    expect(offenders(/(?<![:\w-])bg-brand-accent/)).toEqual([]);
    // the mark itself paints with it:
    expect(SOURCES.find((x) => x.file.endsWith("components/Mark.tsx"))!.text).toContain("--brand-accent");
  });
  it("no small text in Signal Teal, and no Signal Teal backgrounds behind text", () => {
    expect(offenders(/(?<![:\w-])text-brand-primary/)).toEqual([]);
    // Opaque Signal Teal behind small text fails AA (4.26:1). Faint tints such as bg-brand-primary/10 are fine.
    expect(offenders(/(?<![:\w-])bg-brand-primary(?!\/)/)).toEqual([]);
  });
  it("uses Geist, a deliberate departure from the kit's IBM Plex, chosen by the owner (see frontend/README.md)", () => {
    const layout = SOURCES.find((x) => x.file.endsWith("app/layout.tsx"))!.text;
    expect(layout).toContain("geist/font/sans");
    expect(layout).toContain("geist/font/mono");
    expect(css).toContain("--font-geist-sans");
  });
});
