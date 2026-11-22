import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { SESSION_COOKIE } from "@/lib/session";

/**
 * OPTIMISTIC check only: no cookie means "go sign in". It does not prove the session is valid;
 * the real authorization happens in the FastAPI backend on every API call.
 * (We deliberately do not bounce signed-in users away from /login: an expired cookie would loop.)
 */
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (pathname === "/" || pathname === "/login") return NextResponse.next(); // the landing page and sign-in are public
  if (!request.cookies.has(SESSION_COOKIE)) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
