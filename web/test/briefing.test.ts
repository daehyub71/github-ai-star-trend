import { describe, expect, it } from "vitest";

import { parseBriefing, parseCard } from "@/lib/markdown";

const BRIEF = `---
week: 2026-10-18
as_of: 2026-10-24
---
# 이번 주 AI 트렌드 — 2026-10-18 ~ 2026-10-24

에이전트 스킬이 이번 주 흐름을 이끌었다.

## 뜨는 카테고리 · 식는 카테고리
| a | b |
|---|---|

## 왜 지금 — 주목할 저장소
- [o/a](https://github.com/o/a) — 출시와 HN 이 겹쳤다. (확인)
- [o/b](https://github.com/o/b) — 릴리스가 매일 나왔다. (확인)

## 시사점
- 스킬이 주류가 됐다. [o/a](https://github.com/o/a) (추정)
`;

const CARD = `---
repo: o/a
repo_id: 1
week: 2026-10-18
as_of: 2026-10-24
generated: 2026-10-28
fingerprint: abcdef0123456789:claude-opus-5-5:medium
evidence: 16
gate_checked: 40
gate_excluded: 1
---
# o/a

## ① 3줄 요약
- **무엇인지** — 도구다.

## ② 숫자
| 항목 | 값 |
|---|---|

## ⑧ 변경 기록
- 2026-10-28 처음 작성

## 근거
- E1 [x](https://e.com)
`;

describe("markdown parsing", () => {
  it("reads the briefing headline, why-now items and front matter", () => {
    const b = parseBriefing(BRIEF);
    expect(b.front.week).toBe("2026-10-18");
    expect(b.headline).toBe("에이전트 스킬이 이번 주 흐름을 이끌었다.");
    expect(b.whyNow).toEqual([
      "[o/a](https://github.com/o/a) — 출시와 HN 이 겹쳤다. (확인)",
      "[o/b](https://github.com/o/b) — 릴리스가 매일 나왔다. (확인)",
    ]);
    expect(b.body.startsWith("에이전트 스킬")).toBe(true);
  });

  it("splits a card into numbered sections plus the evidence list", () => {
    const c = parseCard(CARD);
    expect(c.front).toMatchObject({ repo: "o/a", as_of: "2026-10-24", gate_excluded: "1" });
    expect(c.sections.map((s) => [s.no, s.title, s.id])).toEqual([
      ["01", "3줄 요약", "s1"], ["02", "숫자", "s2"], ["08", "변경 기록", "s8"],
    ]);
    expect(c.evidence?.startsWith("- E1")).toBe(true);
    expect(c.sections[0].body.trim()).toBe("- **무엇인지** — 도구다.");
  });

  it("reads files edited on Windows (CRLF) the same way", () => {
    const c = parseCard(CARD.replace(/\n/g, "\r\n"));
    expect(c.front.repo).toBe("o/a");
    expect(c.sections).toHaveLength(3);
  });
});
