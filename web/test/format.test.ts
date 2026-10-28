import { describe, expect, it } from "vitest";

import { fmtInt, fmtPct, fmtSigned, isFresh, mmdd, splitName, weekRange } from "@/lib/format";

describe("format", () => {
  it("formats numbers with thousands separators and signs", () => {
    expect(fmtInt(1234567)).toBe("1,234,567");
    expect(fmtSigned(17188)).toBe("+17,188");
    expect(fmtSigned(-30)).toBe("−30");
    expect(fmtInt(null)).toBe("—");
    expect(fmtPct(0.4734)).toBe("47.3%");
  });

  it("formats week ranges across months and years", () => {
    expect(weekRange("2026-10-18", "2026-10-24")).toBe("2026년 10월 18일 – 24일");
    expect(weekRange("2026-10-25", "2026-10-31")).toBe("2026년 10월 25일 – 31일");
    expect(weekRange("2026-11-29", "2026-12-05")).toBe("2026년 11월 29일 – 12월 5일");
    expect(weekRange("2026-12-27", "2027-01-02")).toBe("2026년 12월 27일 – 2027년 1월 2일");
    expect(mmdd("2026-09-07")).toBe("09.07");
  });

  it("treats repos created under 30 days before the week end as fresh", () => {
    expect(isFresh("2026-10-01", "2026-10-24")).toBe(true);
    expect(isFresh("2026-09-20", "2026-10-24")).toBe(false);
  });

  it("splits owner and repo for the two-tone name", () => {
    expect(splitName("google-research/harness2")).toEqual({ owner: "google-research/", repo: "harness2" });
  });
});
