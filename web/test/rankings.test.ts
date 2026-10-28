import { describe, expect, it } from "vitest";

import { buildSections, catBars, codeFacts } from "@/lib/rankings";

import { entry, NAMES, week } from "./helpers";

describe("rankings", () => {
  it("builds four axis sections with AI and all tabs in the agreed order", () => {
    const secs = buildSections(week(), NAMES, new Set());
    expect(secs.map((s) => s.title)).toEqual(["지금 뜨는 저장소", "새로 뜨는 저장소", "규모 대비 급성장", "누적 스타 TOP"]);
    expect(secs[0].all).toHaveLength(15);
    expect(secs[0].ai).toHaveLength(8);
    expect(secs[1].ai).toBeNull();                      // 판정 전이면 AI 탭 없음
  });

  it("shows value and sub text per axis from code numbers", () => {
    const w = week();
    w.axes.gain!.all[0] = entry(1, "o/r1", { gain: 17188, stars_end: 19218 });
    w.axes.growth!.all[0] = entry(1, "o/r1", { growth: 8.4669, start_stars: 2030, stars_end: 19218 });
    w.axes.total!.all[0] = entry(1, "o/r1", { stars_end: 392915, rank: 2, prev_rank: 4 });
    const [gain, fresh, growth, total] = buildSections(w, NAMES, new Set());
    expect(gain.all[0]).toMatchObject({ value: "+17,188", sub: "누적 19,218" });
    expect(fresh.all[0].sub).toBe("생성 10.10");
    expect(growth.all[0]).toMatchObject({ value: "+846.7%", sub: "2,030 → 19,218" });
    expect(total.all[0]).toMatchObject({ value: "392,915", sub: "▲ 2 (지난 주 4위)" });
  });

  it("labels rows with category, type, fresh and flag chips", () => {
    const w = week();
    w.axes.gain!.all[0] = entry(1, "o/r1", {
      category: "mcp-tools", type: "큐레이션 목록", created: "2026-10-12",
      flags: [{ kind: "peak_day", label: "하루 몰림 69%", value: 69 }],
    });
    w.axes.gain!.all[1] = entry(2, "o/r2", { is_ai: false, category: null });
    w.axes.gain!.all[2] = entry(3, "o/r3", { is_ai: null, category: null });
    const rows = buildSections(w, NAMES, new Set())[0].all;
    expect(rows[0].chips).toEqual([
      { kind: "cat", label: "MCP 서버·도구" }, { kind: "type", label: "큐레이션 목록" },
      { kind: "fresh", label: "30일 이내" }, { kind: "flag", label: "하루 몰림 69%" },
    ]);
    expect(rows[1].chips[0]).toEqual({ kind: "no", label: "AI 아님" });
    expect(rows[2].chips[0]).toEqual({ kind: "pending", label: "분류 전" });
  });

  it("links to the card when one exists, otherwise to GitHub", () => {
    const rows = buildSections(week(), NAMES, new Set(["o__r1"]))[0].all;
    expect(rows[0].href).toBe("/repo/o/r1");
    expect(rows[1].href).toBe("https://github.com/o/r2");
    expect(rows[0]).toMatchObject({ owner: "o/", repo: "r1" });
  });

  it("counts categories in the AI gain tab for the side bars", () => {
    const w = week();
    w.axes.gain!.ai = [entry(1, "a/a", { category: "rag" }), entry(2, "b/b", { category: "rag" }),
      entry(3, "c/c", { category: "mcp-tools" })];
    expect(catBars(w, NAMES)).toEqual([{ label: "RAG·검색", count: 2, width: "100%" },
      { label: "MCP 서버·도구", count: 1, width: "50%" }]);
  });

  it("writes code facts when there is no briefing", () => {
    const facts = codeFacts(week(), NAMES);
    expect(facts.headline).toContain("o/r1");
    expect(facts.items.length).toBeGreaterThan(0);
  });
});
