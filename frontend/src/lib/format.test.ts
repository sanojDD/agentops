import { describe, expect, it } from "vitest";
import { errorHint, formatBytes, formatDuration, outcome, relativeTime } from "./format";

describe("format", () => {
  it("formats bytes", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(2_000_000)).toBe("2.0 MB");
  });

  it("formats durations", () => {
    expect(formatDuration(850)).toBe("850 ms");
    expect(formatDuration(3200)).toBe("3.2 s");
    expect(formatDuration(null)).toBe("n/a");
  });

  it("formats relative time", () => {
    const now = new Date("2026-10-18T12:00:00Z").getTime();
    expect(relativeTime("2026-10-18T11:59:50Z", now)).toBe("just now");
    expect(relativeTime("2026-10-18T11:55:00Z", now)).toBe("5 min ago");
    expect(relativeTime("2026-10-18T09:00:00Z", now)).toBe("3 h ago");
    expect(relativeTime("2026-10-16T12:00:00Z", now)).toBe("2 d ago");
    expect(relativeTime("not a date", now)).toBe("");
  });

  it("describes outcomes", () => {
    expect(outcome({ fallback: false, fallbackReason: null, errorKind: null })).toEqual({
      label: "Answered",
      tone: "ok",
    });
    expect(outcome({ fallback: true, fallbackReason: "no_evidence", errorKind: null })).toEqual({
      label: "Not in documents",
      tone: "warn",
    });
    expect(outcome({ fallback: false, fallbackReason: null, errorKind: "rate_limited" })).toEqual({
      label: "Rate limited",
      tone: "error",
    });
    expect(errorHint("rate_limited")).toContain("rate limit");
  });
});
