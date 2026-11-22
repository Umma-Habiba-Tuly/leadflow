import { describe, expect, it } from "vitest";
import { messageFromBackend } from "@/lib/errors";

describe("messageFromBackend", () => {
  it("uses the backend's own sentence when it sends one", () => {
    expect(messageFromBackend(400, { detail: "Complete your sender profile first (missing: postal_address)" })).toBe(
      "Complete your sender profile first (missing: postal_address)",
    );
  });
  it("makes a validation error readable", () => {
    const body = { detail: [{ loc: ["body", "smtp_port"], msg: "Input should be less than or equal to 65535" }] };
    expect(messageFromBackend(422, body)).toBe("smtp port: Input should be less than or equal to 65535");
  });
  it("strips pydantic's 'Value error, ' prefix", () => {
    const body = { detail: [{ loc: ["body", "from_name"], msg: "Value error, must not contain control characters or line breaks" }] };
    expect(messageFromBackend(422, body)).toBe("from name: must not contain control characters or line breaks");
  });
  it("handles a validation error with no field", () => {
    expect(messageFromBackend(422, { detail: [{ msg: "bad" }] })).toBe("bad");
  });
  it("falls back by status when there is no detail", () => {
    expect(messageFromBackend(401, null)).toMatch(/sign in again/i);
    expect(messageFromBackend(404, {})).toMatch(/not found/i);
    expect(messageFromBackend(413, undefined)).toMatch(/too large/i);
    expect(messageFromBackend(503, "oops")).toMatch(/try again/i);
    expect(messageFromBackend(418, null)).toBe("Something went wrong.");
  });
  it("never throws on odd input", () => {
    for (const body of [null, undefined, 5, "x", [], { detail: 5 }, { detail: [] }, { detail: [null] }]) {
      expect(() => messageFromBackend(500, body as unknown)).not.toThrow();
    }
  });
});
