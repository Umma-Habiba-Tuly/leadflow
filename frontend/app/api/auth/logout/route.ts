import { NextRequest, NextResponse } from "next/server";
import { isSameOriginRequest } from "@/lib/proxyRules";
import { clearToken } from "@/lib/session";

export async function POST(request: NextRequest) {
  if (!isSameOriginRequest("POST", request.headers.get("origin"), request.headers.get("host"))) {
    return NextResponse.json({ detail: "Forbidden" }, { status: 403 });
  }
  await clearToken();
  return NextResponse.json({ ok: true });
}
