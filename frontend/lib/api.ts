"use client";

import { messageFromBackend } from "@/lib/errors";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

type Options = { method?: string; json?: unknown; form?: FormData };

/** Call the backend through our same-origin proxy. The API token never reaches this code. */
export async function api<T>(path: string, { method = "GET", json, form }: Options = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api/proxy${path}`, {
      method,
      headers: json !== undefined ? { "Content-Type": "application/json" } : undefined, // FormData sets its own boundary
      body: form ?? (json !== undefined ? JSON.stringify(json) : undefined),
    });
  } catch {
    throw new ApiError(0, "Network problem. Check your connection and try again.");
  }
  if (res.status === 401) {
    // A full page load on purpose: it drops every piece of client state once the session has ended.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign("/login");
    throw new ApiError(401, "Your session has ended. Please sign in again.");
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, messageFromBackend(res.status, data));
  return data as T;
}
