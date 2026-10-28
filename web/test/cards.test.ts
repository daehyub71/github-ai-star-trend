import { describe, expect, it } from "vitest";

import { weekCardList } from "@/lib/cards";
import { cardSummary } from "@/lib/markdown";

import { entry, NAMES, week } from "./helpers";

const CARD = `---
repo: o/r1
week: 2026-10-18
---
# o/r1

## ① 3줄 요약
- **무엇인지** — 에이전트를 [격리된 worktree](https://example.com/a)에서 돌리는 앱이다.
- **왜 지금 떴나** — 이번 주 릴리스가 이어졌다.
- **어떤 의미인지** — 여러 에이전트를 한곳에서 다룬다.

## ② 숫자
| 항목 | 값 |
`;

describe("cardSummary", () => {
  it("reads the three summary lines and drops link targets", () => {
    expect(cardSummary(CARD)).toEqual({
      what: "에이전트를 격리된 worktree에서 돌리는 앱이다.",
      why: "이번 주 릴리스가 이어졌다.",
      meaning: "여러 에이전트를 한곳에서 다룬다.",
    });
  });

  it("returns empty lines when the card has no summary", () => {
    expect(cardSummary("# x\n\n## ② 숫자\n")).toEqual({ what: "", why: "", meaning: "" });
  });
});

describe("weekCardList", () => {
  it("lists AI-tab repos that have cards, axis order first, without repeats", () => {
    const w = week();
    w.axes.gain!.ai = [entry(3, "o/r3", { category: "mcp-tools" }), entry(1, "o/r1")];
    w.axes.growth!.ai = [entry(5, "o/r5"), entry(1, "o/r1")];
    w.axes.total!.ai = [entry(9, "o/r9")];
    const briefs = new Map([
      ["o__r1", { what: "w1", why: "y1", meaning: "m1" }],
      ["o__r3", { what: "w3", why: "y3", meaning: "m3" }],
      ["o__r5", { what: "w5", why: "y5", meaning: "m5" }],
      ["o__r7", { what: "w7", why: "y7", meaning: "m7" }],     // 이번 주 AI 탭에 없다
    ]);
    const list = weekCardList(w, briefs, NAMES);
    expect(list.map((c) => c.fullName)).toEqual(["o/r3", "o/r1", "o/r5"]);
    expect(list[0]).toMatchObject({ slug: "o__r3", owner: "o/", repo: "r3", catId: "mcp-tools",
      catName: "MCP 서버·도구", what: "w3", why: "y3", meaning: "m3", href: "/repo/o/r3" });
  });
});
