import { describe, expect, it } from "vitest";

import { buildSections, catBars, codeFacts, heroStats } from "@/lib/rankings";

import { entry, NAMES, week } from "./helpers";

describe("rankings", () => {
  it("builds four axis sections with AI and all tabs in the agreed order", () => {
    const secs = buildSections(week(), NAMES, new Map());
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
    const [gain, fresh, growth, total] = buildSections(w, NAMES, new Map());
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
    const rows = buildSections(w, NAMES, new Map())[0].all;
    expect(rows[0].chips).toEqual([
      { kind: "cat", label: "MCP 서버·도구", catId: "mcp-tools" }, { kind: "type", label: "큐레이션 목록" },
      { kind: "fresh", label: "30일 이내" }, { kind: "flag", label: "하루 몰림 69%" },
    ]);
    expect(rows[1].chips[0]).toEqual({ kind: "no", label: "AI 아님" });
    expect(rows[2].chips[0]).toEqual({ kind: "pending", label: "분류 전" });
  });

  it("links to the card when one exists, otherwise to GitHub", () => {
    const rows = buildSections(week(), NAMES, new Map([["o__r1", "이번 주 릴리스."]]))[0].all;
    expect(rows[0].href).toBe("/repo/o/r1");
    expect(rows[1].href).toBe("https://github.com/o/r2");
    expect(rows[0]).toMatchObject({ owner: "o/", repo: "r1" });
  });

  it("marks rows with a card badge and the card's why-now line", () => {
    // 시안 v1.3 — 카드가 있는 행에 '카드' 배지와 '왜 지금' 한 줄
    const rows = buildSections(week(), NAMES, new Map([["o__r1", "이번 주 릴리스."]]))[0].all;
    expect(rows[0]).toMatchObject({ hasCard: true, why: "이번 주 릴리스." });
    expect(rows[0].chips.at(-1)).toEqual({ kind: "card", label: "카드" });
    expect(rows[1]).toMatchObject({ hasCard: false, why: "" });
    expect(rows[1].chips.some((c) => c.kind === "card")).toBe(false);
  });

  it("keeps the category id on rows for the category colors", () => {
    const w = week();
    w.axes.gain!.all[0] = entry(1, "o/r1", { category: "mcp-tools" });
    w.axes.gain!.all[1] = entry(2, "o/r2", { is_ai: false, category: null });
    const rows = buildSections(w, NAMES, new Map())[0].all;
    expect(rows[0].chips[0]).toMatchObject({ kind: "cat", catId: "mcp-tools" });
    expect(rows[1].chips[0].catId).toBeUndefined();
  });

  it("counts categories in the AI gain tab for the side bars", () => {
    const w = week();
    w.axes.gain!.ai = [entry(1, "a/a", { category: "rag" }), entry(2, "b/b", { category: "rag" }),
      entry(3, "c/c", { category: "mcp-tools" })];
    expect(catBars(w, NAMES)).toEqual([{ id: "rag", label: "RAG·검색", count: 2, width: "100%" },
      { id: "mcp-tools", label: "MCP 서버·도구", count: 1, width: "50%" }]);
  });

  it("builds the three hero numbers from the AI tab", () => {
    const w = week();
    w.axes.gain!.ai = [entry(1, "deepseek-ai/DeepInfer", { gain: 22017 }), entry(3, "o/r3")];
    w.axes.growth!.ai = [entry(2, "google-research/harness2", { growth: 8.467 })];
    w.axes.total!.ai = [entry(1, "deepseek-ai/DeepInfer"), entry(7, "o/r7")];
    expect(heroStats(w, 5)).toEqual([
      { value: "+22,017", label: "최다 증가 · DeepInfer" },
      { value: "847%", label: "최고 성장률 · harness2" },
      { value: "4", label: "이번 주 AI 저장소 · 카드 5장" },
    ]);
  });

  it("writes code facts when there is no briefing", () => {
    const facts = codeFacts(week(), NAMES);
    expect(facts.headline).toContain("o/r1");
    expect(facts.items.length).toBeGreaterThan(0);
  });
});
