import { describe, expect, it } from "vitest";

import { repoView } from "@/lib/repotrends";
import type { RepoTrends } from "@/lib/types";

function data(): RepoTrends {
  const weeks = Array.from({ length: 52 }, (_, i) => `w${i}`);
  const r = (id: number, name: string, bits: string, gain4: number, category = "rag") => ({
    id, full_name: name, category, bits: bits.padStart(52, "0"), streak: bits.length - bits.replace(/1+$/, "").length,
    gain4, spark: Array.from({ length: 12 }, (_, k) => k),
  });
  return {
    weeks, axes: ["gain", "fresh", "growth"],
    repos: [
      r(1, "o/old", "1".repeat(30) + "0".repeat(20), 10),     // 오래전에 꾸준했던 저장소 — 최근 12주엔 없다
      r(2, "o/steady", "111111111111", 500),
      r(3, "o/hot", "000000000111", 9000),
      r(4, "o/mid", "000011110000", 800),
    ],
  };
}

describe("repoView", () => {
  it("counts weeks inside the chosen period and drops repos absent from it", () => {
    const rows = repoView(data(), 12, "weeks", 15, new Set());
    expect(rows.map((r) => r.fullName)).toEqual(["o/steady", "o/mid", "o/hot"]);
    expect(rows[0]).toMatchObject({ weeks: 12, bits: "1".repeat(12), streak: 12, rank: 1 });
    expect(rows[2].bits).toHaveLength(12);
  });

  it("uses all 52 weeks for the long period", () => {
    const rows = repoView(data(), 52, "weeks", 15, new Set());
    expect(rows[0]).toMatchObject({ fullName: "o/old", weeks: 30 });
    expect(rows[0].bits).toHaveLength(52);
  });

  it("sorts by recent gain or by streak and keeps the limit", () => {
    expect(repoView(data(), 12, "gain", 15, new Set()).map((r) => r.fullName)).toEqual(["o/hot", "o/mid", "o/steady"]);
    expect(repoView(data(), 12, "streak", 2, new Set()).map((r) => r.fullName)).toEqual(["o/steady", "o/hot"]);
  });

  it("links to the card when there is one", () => {
    const rows = repoView(data(), 12, "weeks", 15, new Set(["o__hot"]));
    const hot = rows.find((r) => r.fullName === "o/hot")!;
    expect(hot).toMatchObject({ hasCard: true, href: "/repo/o/hot" });
    expect(rows[0]).toMatchObject({ hasCard: false, href: "https://github.com/o/steady" });
  });
});
