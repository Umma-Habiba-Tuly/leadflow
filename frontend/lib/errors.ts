/** Turn whatever the backend returned into one short sentence a person can act on. */

type FastApiIssue = { loc?: Array<string | number>; msg?: string };

export function messageFromBackend(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;

  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as FastApiIssue | null;
    if (first && typeof first === "object") {
      const field = Array.isArray(first.loc) ? first.loc.filter((p) => typeof p === "string" && p !== "body").pop() : undefined;
      const msg = (typeof first.msg === "string" ? first.msg : "is invalid").replace(/^Value error, /, "");
      return field ? `${String(field).replace(/_/g, " ")}: ${msg}` : msg;
    }
  }

  if (status === 401) return "Your session has ended. Please sign in again.";
  if (status === 403) return "You are not allowed to do that.";
  if (status === 404) return "That item was not found.";
  if (status === 413) return "That file is too large.";
  if (status === 429) return "Too many requests. Please wait a moment.";
  if (status >= 500) return "The server had a problem. Please try again.";
  return "Something went wrong.";
}
