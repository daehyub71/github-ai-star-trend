import { describe, expect, it } from "vitest";

import { chartData, MAX_SELECTED, trendRows } from "@/lib/trends";
import type { Categories } from "@/lib/types";

import { entry, NAMES, week } from "./helpers";

const CATS: Categories = {
  weeks: ["2026-09-20", "2026-09-27", "2026-10-04", "2026-10-11", "2026-10-18"],
  series: {
    rag: { gain: [100, 100, 100, 100, 200], repos: [1, 1, 1, 1, 2], entrants: [0, 0, 0, 1, 2] },
    "mcp-tools": { gain: [null, 50, 50, 50, 50], repos: [null, 1, 1, 1, 1], entrants: [null, 0, 0, 0, 1] },
    ALL: { gain: [100, 150, 150, 150, 250], repos: [1, 2, 2, 2, 3], entrants: [0, 0, 0, 1, 3] },
  },
  coverage: [0.5, 0.5, 0.5, 0.5, 0.48],
  names: { ...NAMES, ALL: "ALL" },
};

describe("trends", () => {
  it("builds chart points for the chosen period and categories", () => {
    const pts = chartData(CATS, ["ALL", "rag"], 2);
    expect(pts).toEqual([{ week: "10.11", ALL: 150, rag: 100 }, { week: "10.18", ALL: 250, rag: 200 }]);
    expect(MAX_SELECTED).toBe(6);
  });

  it("compares the latest week with the previous four-week average", () => {
    const w = week();
    w.axes.gain!.ai = [entry(1, "o/best", { category: "rag", gain: 900 }), entry(2, "o/next", { category: "rag" })];
    const rows = trendRows(CATS, w);
    const rag = rows.find((r) => r.id === "rag")!;
    expect(rag).toMatchObject({ label: "RAG·검색", gain: 200, vsAvg: 1.0, entrants: 2 });
    expect(rag.repos).toEqual(["o/best", "o/next"]);
    expect(rows.find((r) => r.id === "mcp-tools")!.vsAvg).toBe(0);
    expect(rows.map((r) => r.id)).toEqual(["rag", "mcp-tools"]);          // 이번 주 증가 큰 순, ALL 은 빼고
  });
});
