/**
 * Rules for the browser -> Next.js -> FastAPI proxy. Kept as pure functions so they can be
 * tested without a server. The proxy must NOT be an open relay: only the API calls the
 * dashboard actually makes are allowed, and state-changing calls must come from our own pages.
 */

const ID = "\\d+";

// [method, path pattern]. Anything not listed is refused.
const ALLOWED: Array<[string, RegExp]> = [
  ["GET", /^\/auth\/me$/],
  ["GET", /^\/workspace\/profile$/],
  ["PUT", /^\/workspace\/profile$/],
  ["GET", /^\/campaigns$/],
  ["POST", /^\/campaigns$/],
  ["GET", new RegExp(`^/campaigns/${ID}$`)],
  ["GET", new RegExp(`^/campaigns/${ID}/(leads|drafts|sent|stats)$`)],
  ["POST", new RegExp(`^/campaigns/${ID}/(search|enrich|score|send)$`)],
  ["POST", new RegExp(`^/campaigns/${ID}/leads/import$`)],
  ["POST", new RegExp(`^/campaigns/${ID}/drafts/generate$`)],
  ["PATCH", new RegExp(`^/drafts/${ID}$`)],
  ["GET", /^\/mailboxes$/],
  ["POST", /^\/mailboxes$/],
  ["PATCH", new RegExp(`^/mailboxes/${ID}$`)],
  ["POST", new RegExp(`^/mailboxes/${ID}/check$`)],
  ["GET", /^\/suppressions$/],
  ["POST", /^\/suppressions$/],
];

export function isAllowedProxyCall(method: string, path: string): boolean {
  // Reject anything that tries to climb out of the allow-listed shape before matching.
  if (path.includes("..") || path.includes("//") || path.includes("\\") || path.includes("%")) return false;
  const m = method.toUpperCase();
  return ALLOWED.some(([allowedMethod, pattern]) => allowedMethod === m && pattern.test(path));
}

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

/**
 * CSRF defence in depth (the cookie is also SameSite=Lax). For state-changing requests the
 * browser always sends an Origin header; it must be our own host.
 */
export function isSameOriginRequest(method: string, origin: string | null, host: string | null): boolean {
  if (SAFE_METHODS.has(method.toUpperCase())) return true;
  if (!origin || !host) return false; // a state-changing request with no Origin is not from our pages
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}

/** Join the catch-all route segments into a backend path, refusing anything odd. */
export function backendPathFromSegments(segments: string[]): string | null {
  if (segments.length === 0) return null;
  if (segments.some((s) => s === "" || s === "." || s === ".." || /[\\/%]/.test(s))) return null;
  return "/" + segments.join("/");
}
