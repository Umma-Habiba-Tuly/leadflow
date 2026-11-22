import { NextRequest, NextResponse } from "next/server";
import { ApiError, callBackend } from "@/lib/backend";
import { isSameOriginRequest } from "@/lib/proxyRules";
import { setToken } from "@/lib/session";

export async function POST(request: NextRequest) {
  if (!isSameOriginRequest("POST", request.headers.get("origin"), request.headers.get("host"))) {
    return NextResponse.json({ detail: "Forbidden" }, { status: 403 });
  }
  const body = await request.json().catch(() => null);
  if (!body || typeof body.email !== "string" || typeof body.password !== "string" || !body.email || !body.password) {
    return NextResponse.json({ detail: "Enter your email and password." }, { status: 422 });
  }
  try {
    const { access_token } = await callBackend<{ access_token: string }>("/auth/login", {
      method: "POST",
      json: { email: body.email, password: body.password },
    });
    await setToken(access_token);
    return NextResponse.json({ ok: true });
  } catch (err) {
    const e = err instanceof ApiError ? err : new ApiError(500, "Sign in failed.");
    return NextResponse.json({ detail: e.message }, { status: e.status });
  }
}
