import { describe, expect, it } from "vitest";
import { hostOf, safeHttpUrl } from "@/lib/url";

describe("safeHttpUrl: lead websites are untrusted", () => {
  it.each([
    ["https://brightsmile.example", "https://brightsmile.example/"],
    ["http://a.example/path?x=1", "http://a.example/path?x=1"],
    ["brightsmile.example", "https://brightsmile.example/"],
    ["  www.a.example  ", "https://www.a.example/"],
  ])("accepts %s", (input, expected) => {
    expect(safeHttpUrl(input)).toBe(expected);
  });

  it.each([
    "javascript:alert(1)",
    "JaVaScRiPt:alert(1)",
    "  javascript:alert(document.cookie)",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:msgbox(1)",
    "file:///etc/passwd",
    "ftp://a.example",
    "mailto:x@a.example",
    "http://",
    "localhost",
    "not a url",
    "",
    null,
    undefined,
  ])("refuses %j", (input) => {
    expect(safeHttpUrl(input as string | null | undefined)).toBeNull();
  });
});

describe("hostOf", () => {
  it("shows a tidy host", () => {
    expect(hostOf("https://www.brightsmile.example/about")).toBe("brightsmile.example");
    expect(hostOf("garbage")).toBe("garbage");
  });
});
