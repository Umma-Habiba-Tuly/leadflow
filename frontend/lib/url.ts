/**
 * Lead websites come from CSV uploads and web search, so they are untrusted text. Rendering one
 * as <a href> without checking lets "javascript:..." run script when someone clicks it.
 * Returns a safe http(s) URL, or null.
 */
export function safeHttpUrl(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const text = raw.trim();
  // A bare "example.com" is a normal thing to find in a CSV.
  const candidate = /^[a-z][a-z0-9+.-]*:/i.test(text) ? text : `https://${text}`;
  try {
    const url = new URL(candidate);
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    if (!url.hostname.includes(".")) return null;
    return url.href;
  } catch {
    return null;
  }
}

export function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}
