import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { BACKEND_URL } from "@/lib/backend";
import { backendPathFromSegments, isAllowedProxyCall, isSameOriginRequest } from "@/lib/proxyRules";
import { SESSION_COOKIE, getToken } from "@/lib/session";

/**
 * Browser -> here -> FastAPI. The browser never holds the API token: we read it from the httpOnly
 * cookie and attach it. This is NOT an open relay: only allow-listed calls pass (lib/proxyRules.ts).
 */
async function handle(request: NextRequest, ctx: RouteContext<"/api/proxy/[...path]">) {
  const { path } = await ctx.params;
  const method = request.method;
  const backendPath = backendPathFromSegments(path);

  if (!backendPath || !isAllowedProxyCall(method, backendPath)) {
    return NextResponse.json({ detail: "Not found" }, { status: 404 });
  }
  if (!isSameOriginRequest(method, request.headers.get("origin"), request.headers.get("host"))) {
    return NextResponse.json({ detail: "Forbidden" }, { status: 403 });
  }
  const token = await getToken();
  if (!token) return NextResponse.json({ detail: "Not signed in" }, { status: 401 });

  const hasBody = method !== "GET" && method !== "HEAD";
  const contentType = request.headers.get("content-type");
  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND_URL}${backendPath}${request.nextUrl.search}`, {
      method,
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${token}`,
        ...(contentType ? { "Content-Type": contentType } : {}), // keeps the multipart boundary for CSV uploads
      },
      body: hasBody ? request.body : undefined,
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(180_000), // AI scoring/drafting and sending can take a while
      ...(hasBody ? { duplex: "half" } : {}),
    } as RequestInit);
  } catch {
    return NextResponse.json({ detail: "Cannot reach the LeadFlow server. Is the backend running?" }, { status: 502 });
  }

  if (upstream.status === 401) (await cookies()).delete(SESSION_COOKIE); // token expired or revoked
  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" }, // never relay Set-Cookie etc.
  });
}

export { handle as GET, handle as POST, handle as PUT, handle as PATCH };
