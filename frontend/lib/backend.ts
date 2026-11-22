import { redirect } from "next/navigation";
import { messageFromBackend } from "@/lib/errors";
import { getToken } from "@/lib/session";

/** Server-side address of the FastAPI backend. Never exposed to the browser. */
export const BACKEND_URL = (process.env.BACKEND_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

type CallOptions = { method?: string; token?: string | null; json?: unknown };

/** Call the backend from the server. Throws ApiError (status 502 if it can't be reached). */
export async function callBackend<T>(path: string, { method = "GET", token, json }: CallOptions = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BACKEND_URL}${path}`, {
      method,
      headers: {
        Accept: "application/json",
        ...(json !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: json !== undefined ? JSON.stringify(json) : undefined,
      cache: "no-store",
      signal: AbortSignal.timeout(30_000),
    });
  } catch {
    throw new ApiError(502, "Cannot reach the LeadFlow server. Is the backend running?");
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, messageFromBackend(res.status, data));
  return data as T;
}

/**
 * Fetch for Server Components. No session, or a rejected one, sends the visitor to /login.
 * (The cookie itself can only be cleared in a route handler, which /login's flow does on sign-in.)
 */
export async function serverApi<T>(path: string): Promise<T> {
  const token = await getToken();
  if (!token) redirect("/login");
  try {
    return await callBackend<T>(path, { token });
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) redirect("/login");
    throw err;
  }
}
