import { cookies } from "next/headers";

export const SESSION_COOKIE = "lf_token";
const ONE_DAY = 60 * 60 * 24; // same lifetime as the backend's access token

/** The backend's JWT lives in an httpOnly cookie: page JavaScript can never read it, so an XSS bug cannot steal it. */
export async function getToken(): Promise<string | null> {
  return (await cookies()).get(SESSION_COOKIE)?.value ?? null;
}

export async function setToken(token: string): Promise<void> {
  (await cookies()).set(SESSION_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: ONE_DAY,
  });
}

export async function clearToken(): Promise<void> {
  (await cookies()).delete(SESSION_COOKIE);
}
