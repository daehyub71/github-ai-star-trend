import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { AboutContent } from "@/components/AboutContent";
import { SiteHeader } from "@/components/SiteHeader";

afterEach(cleanup);

describe("소개·방법론 (NFR-11, 시안 v1.4)", () => {
  it("states the numbers are self-computed and names the biases", () => {
    render(<AboutContent />);
    const text = document.body.textContent ?? "";
    for (const must of ["자체 산출값", "GitHub 의 공식 지표가 아니", "스타 ≠ 사용량", "생존 편향", "가짜 스타",
      "사람이 검토하지 않습니다", "96.7%", "86.8%"]) {
      expect(text, must).toContain(must);
    }
  });

  it("has the six sections in order with a table of contents", () => {
    render(<AboutContent />);
    const heads = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent?.replace(/^\d+/, ""));
    expect(heads).toEqual(["이 사이트는", "숫자는 어떻게", "AI 저장소 판정", "카드·브리핑은 이렇게 씁니다AI 작성",
      "한계와 편향", "데이터와 코드"]);
    expect(screen.getByRole("navigation", { name: "이 페이지 목차" }).querySelectorAll("a")).toHaveLength(6);
  });
});

describe("머리 메뉴", () => {
  it("has the four screens and marks the current one", () => {
    render(<SiteHeader current="archive" />);
    const links = screen.getByRole("navigation", { name: "주요 화면" }).querySelectorAll("a");
    expect([...links].map((a) => a.textContent)).toEqual(["이번 주", "저장소 추이", "주간 아카이브", "소개·방법론"]);
    expect(screen.getByRole("link", { name: "주간 아카이브" }).getAttribute("aria-current")).toBe("page");
  });
});
