import { describe, expect, it } from "vitest";

import { cardSlugsForWeek, weekCardList } from "@/lib/cards";
import { cardSummary, parseCard, EVIDENCE_TITLE_MAX } from "@/lib/markdown";

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

describe("cardSlugsForWeek — 그 주 화면에 필요한 카드만 (P4-4)", () => {
  it("collects the repos shown in any tab of any axis, once each", () => {
    // 주 화면이 카드를 모두 읽으면 카드가 쌓일수록 화면 하나가 느려진다(합성 5,460장에서 60초 초과)
    const w = week(1);
    w.axes.gain!.ai = [entry(1, "o/a"), entry(2, "o/b")];
    w.axes.gain!.all = [entry(1, "o/a"), entry(9, "x/y")];
    w.axes.total!.ai = [entry(2, "o/b")];
    expect([...cardSlugsForWeek(w)].sort()).toEqual(["o__a", "o__b", "o__r1", "x__y"]);
  });
});

describe("parseCard — evidence titles (결정 56 · NFR-9)", () => {
  it("shortens long evidence titles but keeps links and the rest of the line", () => {
    const long = "23K views · " + "아주 긴 게시글 본문 ".repeat(80);
    const md = `# o/r\n\n## ① 3줄 요약\n- x\n\n## 근거\n- E1 [o/r](https://github.com/o/r) — GitHub\n- E9 [${long}](https://example.com/post) — 웹 검색 · 2026-10-20\n`;
    const lines = parseCard(md).evidence!.split("\n");
    expect(lines[0]).toBe("- E1 [o/r](https://github.com/o/r) — GitHub");
    const title = lines[1].slice(lines[1].indexOf("[") + 1, lines[1].lastIndexOf("]("));
    expect(title.length).toBeLessThanOrEqual(EVIDENCE_TITLE_MAX);
    expect(title.endsWith("…")).toBe(true);
    expect(lines[1].endsWith("](https://example.com/post) — 웹 검색 · 2026-10-20")).toBe(true);
  });
});
