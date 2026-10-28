import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { RankingSections } from "@/components/RankingSections";
import { buildSections } from "@/lib/rankings";

import { NAMES, week } from "./helpers";

afterEach(cleanup);

describe("RankingSections", () => {
  it("starts on the AI tab with five rows per axis and expands to fifteen", () => {
    render(<RankingSections sections={buildSections(week(), NAMES, new Map())} />);
    expect(screen.getByRole("button", { name: "AI" }).getAttribute("aria-pressed")).toBe("true");
    const gain = screen.getByRole("region", { name: "지금 뜨는 저장소" });
    expect(gain.querySelectorAll("a.rank-row")).toHaveLength(5);
    fireEvent.click(screen.getAllByRole("button", { name: "펼치기 · 15위까지" })[0]);
    expect(gain.querySelectorAll("a.rank-row")).toHaveLength(8);       // AI 탭은 8개뿐
    fireEvent.click(screen.getByRole("button", { name: "전체" }));
    expect(gain.querySelectorAll("a.rank-row")).toHaveLength(15);
  });

  it("shows medals for the top three and the why-now line for carded rows", () => {
    render(<RankingSections sections={buildSections(week(), NAMES, new Map([["o__r1", "논문 공개 뒤 급등했다."]]))} />);
    const gain = screen.getByRole("region", { name: "지금 뜨는 저장소" });
    const ranks = [...gain.querySelectorAll(".rank-no")].map((n) => n.className);
    expect(ranks.slice(0, 4)).toEqual(["rank-no medal-1", "rank-no medal-2", "rank-no medal-3", "rank-no"]);
    expect(gain.querySelector(".why")?.textContent).toBe("왜 지금 · 논문 공개 뒤 급등했다.");
    expect(gain.querySelectorAll(".why")).toHaveLength(1);
  });

  it("says when an AI tab is not classified yet", () => {
    render(<RankingSections sections={buildSections(week(), NAMES, new Map())} />);
    const fresh = screen.getByRole("region", { name: "새로 뜨는 저장소" });
    expect(fresh.textContent).toContain("아직 판정 전");
  });
});
