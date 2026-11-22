import { NextRequest, NextResponse } from "next/server";
import { ApiError, callBackend } from "@/lib/backend";
import { isSameOriginRequest } from "@/lib/proxyRules";
import { setToken } from "@/lib/session";

export async function POST(request: NextRequest) {
  if (!isSameOriginRequest("POST", request.headers.get("origin"), request.headers.get("host"))) {
    return NextResponse.json({ detail: "Forbidden" }, { status: 403 });
  }
  const body = await request.json().catch(() => null);
  const fields = ["email", "password", "workspace_name"] as const;
  if (!body || fields.some((f) => typeof body[f] !== "string" || !body[f])) {
    return NextResponse.json({ detail: "Enter your email, a password and a company name." }, { status: 422 });
  }
  try {
    const { access_token } = await callBackend<{ access_token: string }>("/auth/register", {
      method: "POST",
      json: { email: body.email, password: body.password, workspace_name: body.workspace_name },
    });
    await setToken(access_token);
    return NextResponse.json({ ok: true }, { status: 201 });
  } catch (err) {
    const e = err instanceof ApiError ? err : new ApiError(500, "Could not create the account.");
    return NextResponse.json({ detail: e.message }, { status: e.status });
  }
}
