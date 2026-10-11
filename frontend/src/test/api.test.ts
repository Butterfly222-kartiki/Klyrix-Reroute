import { describe, expect, it } from "vitest";
import { hhmm } from "@/lib/api";

describe("hhmm", () => {
  it("formats minutes since midnight", () => {
    expect(hhmm(630)).toBe("10:30");
    expect(hhmm(479.6)).toBe("08:00");
    expect(hhmm(null)).toBe("—");
  });
});
