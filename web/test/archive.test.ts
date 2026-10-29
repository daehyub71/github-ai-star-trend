import { describe, expect, it } from "vitest";

import { archiveRow, barHeights, monthGroups, monthLabels } from "@/lib/archive";

import { entry, week } from "./helpers";

describe("archive — 주간 아카이브 (시안 v1.4)", () => {
  it("summarises a week: AI gain leader, distinct AI repos, leading category, fresh leader", () => {
    const w = week();
    w.axes.gain!.ai = [entry(1, "o/top", { gain: 69361, category: "mcp-tools" }),
      entry(3, "o/b", { category: "agent-skills" }), entry(5, "o/c", { category: "mcp-tools" })];
    w.axes.fresh!.ai = [entry(9, "o/new")];
    w.axes.growth!.ai = [entry(1, "o/top")];
    w.axes.total!.ai = [entry(11, "o/big")];
    expect(archiveRow(w, true)).toEqual({
      week: "2026-10-18", end: "2026-10-24", top: "o/top", gain: 69361, topCat: "mcp-tools",
      n: 5, lead: "mcp-tools", fresh: "o/new", brief: true,
    });
  });

  it("copes with a week whose AI tab is not classified", () => {
    const w = week();
    w.axes.gain!.ai = null;
    w.axes.fresh!.ai = null;
    w.axes.growth!.ai = null;
    w.axes.total!.ai = null;
    expect(archiveRow(w, false)).toMatchObject({ top: null, gain: 0, n: 0, lead: null, fresh: null, brief: false });
  });

  it("groups weeks by the month they start in, newest first", () => {
    const rows = ["2026-09-27", "2026-10-04", "2026-10-11", "2026-10-18"].map((d) => ({
      week: d, end: d, top: null, gain: 0, topCat: null, n: 0, lead: null, fresh: null, brief: false }));
    const g = monthGroups(rows);
    expect(g.map((m) => m.label)).toEqual(["2026년 10월", "2026년 9월"]);
    expect(g[0].rows.map((r) => r.week)).toEqual(["2026-10-18", "2026-10-11", "2026-10-04"]);
  });

  it("labels the axis only where the month changes, with the year on the first week and January", () => {
    expect(monthLabels(["2025-12-21", "2025-12-28", "2026-01-04", "2026-01-11", "2026-02-01"]))
      .toEqual(["25.12", "", "26.01", "", "02"]);
  });

  it("skips a label that would sit right next to the previous one (25.10 then 11 overlapped)", () => {
    expect(monthLabels(["2025-10-26", "2025-11-02", "2025-11-09", "2025-12-07"])).toEqual(["25.10", "", "", "12"]);
  });

  it("scales bars by square root so one huge week does not flatten the rest", () => {
    expect(barHeights([100, 400, 0], 120)).toEqual([60, 120, 3]);
  });
});
