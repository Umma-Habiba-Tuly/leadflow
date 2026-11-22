import { describe, expect, it } from "vitest";
import { backendPathFromSegments, isAllowedProxyCall, isSameOriginRequest } from "@/lib/proxyRules";

describe("isAllowedProxyCall: only what the dashboard actually uses", () => {
  const allowed: Array<[string, string]> = [
    ["GET", "/auth/me"],
    ["GET", "/campaigns"],
    ["POST", "/campaigns"],
    ["GET", "/campaigns/12"],
    ["GET", "/campaigns/12/leads"],
    ["GET", "/campaigns/12/stats"],
    ["POST", "/campaigns/12/score"],
    ["POST", "/campaigns/12/leads/import"],
    ["POST", "/campaigns/12/drafts/generate"],
    ["POST", "/campaigns/12/send"],
    ["PATCH", "/drafts/7"],
    ["POST", "/mailboxes"],
    ["PATCH", "/mailboxes/3"],
    ["POST", "/mailboxes/3/check"],
    ["PUT", "/workspace/profile"],
    ["POST", "/suppressions"],
  ];
  it.each(allowed)("allows %s %s", (method, path) => {
    expect(isAllowedProxyCall(method, path)).toBe(true);
  });

  const refused: Array<[string, string, string]> = [
    ["GET", "/docs", "API docs"],
    ["GET", "/openapi.json", "schema"],
    ["POST", "/auth/login", "has its own route that sets the cookie"],
    ["POST", "/auth/register", "has its own route"],
    ["GET", "/u/sometoken", "public unsubscribe page is not for the dashboard"],
    ["POST", "/u/sometoken", "must never be triggered from the dashboard"],
    ["DELETE", "/campaigns/12", "no such call exists"],
    ["PUT", "/campaigns/12", "wrong method"],
    ["GET", "/campaigns/abc", "id must be numeric"],
    ["GET", "/campaigns/12/../mailboxes", "path traversal"],
    ["GET", "/campaigns/12/%2e%2e/mailboxes", "encoded traversal"],
    ["GET", "/campaigns//12", "double slash"],
    ["GET", "/campaigns/12/leads/import", "wrong method for that path"],
    ["POST", "/campaigns/12/leads", "wrong method"],
    ["GET", "/health", "not needed"],
    ["GET", "", "empty"],
    ["GET", "/campaigns/12/leads?x=1", "query must be passed separately, not inside the path"],
  ];
  it.each(refused)("refuses %s %s (%s)", (method, path) => {
    expect(isAllowedProxyCall(method, path)).toBe(false);
  });

  it("is case-insensitive about the method but strict about the path", () => {
    expect(isAllowedProxyCall("get", "/campaigns")).toBe(true);
    expect(isAllowedProxyCall("GET", "/Campaigns")).toBe(false);
  });
});

describe("isSameOriginRequest: CSRF defence in depth", () => {
  it("lets reads through", () => {
    expect(isSameOriginRequest("GET", null, "app.example")).toBe(true);
  });
  it("accepts a state-changing request from our own origin", () => {
    expect(isSameOriginRequest("POST", "https://app.example", "app.example")).toBe(true);
    expect(isSameOriginRequest("PATCH", "http://localhost:3000", "localhost:3000")).toBe(true);
  });
  it("refuses another site", () => {
    expect(isSameOriginRequest("POST", "https://evil.example", "app.example")).toBe(false);
  });
  it("refuses look-alike hosts", () => {
    expect(isSameOriginRequest("POST", "https://app.example.evil.com", "app.example")).toBe(false);
    expect(isSameOriginRequest("POST", "https://evilapp.example", "app.example")).toBe(false);
  });
  it("refuses a state-changing request with no Origin, or a malformed one", () => {
    expect(isSameOriginRequest("POST", null, "app.example")).toBe(false);
    expect(isSameOriginRequest("POST", "not a url", "app.example")).toBe(false);
    expect(isSameOriginRequest("POST", "https://app.example", null)).toBe(false);
  });
  it("treats the literal 'null' origin (sandboxed iframes) as foreign", () => {
    expect(isSameOriginRequest("POST", "null", "app.example")).toBe(false);
  });
});

describe("backendPathFromSegments", () => {
  it("joins ordinary segments", () => {
    expect(backendPathFromSegments(["campaigns", "12", "leads"])).toBe("/campaigns/12/leads");
  });
  it.each([[[]], [[""]], [["campaigns", ".."]], [["campaigns", "."]], [["a/b"]], [["a\\b"]], [["%2e%2e"]]])(
    "refuses %j",
    (segments) => {
      expect(backendPathFromSegments(segments as string[])).toBeNull();
    },
  );
});
