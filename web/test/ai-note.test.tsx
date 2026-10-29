import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { AiNote } from "@/components/AiNote";
import { SiteFooter } from "@/components/SiteHeader";

afterEach(cleanup);

// 결정 56 — 사이트 공개. 카드·브리핑은 사람이 검토하지 않은 AI 글이라는 것을 화면에 밝힌다
describe("AI 작성 안내", () => {
  it("tells readers a card is an unreviewed AI summary with sources", () => {
    render(<AiNote kind="card" />);
    const note = screen.getByRole("note");
    expect(note.textContent).toContain("AI");
    expect(note.textContent).toContain("사람이 검토하지 않았");
    expect(note.textContent).toContain("출처");
    expect(note.textContent).toContain("숫자는 GitHub API");
  });

  it("uses the briefing wording on the briefing page", () => {
    render(<AiNote kind="briefing" />);
    expect(screen.getByRole("note").textContent).toContain("브리핑");
  });

  it("keeps the notice in the footer of every page", () => {
    render(<SiteFooter />);
    expect(screen.getByRole("contentinfo").textContent).toContain("AI 가 쓴 요약");
  });
});
