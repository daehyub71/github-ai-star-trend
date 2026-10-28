import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { RankingSections } from "@/components/RankingSections";
import { buildSections } from "@/lib/rankings";

import { NAMES, week } from "./helpers";

afterEach(cleanup);

describe("RankingSections", () => {
  it("starts on the AI tab with five rows per axis and expands to fifteen", () => {
    render(<RankingSections sections={buildSections(week(), NAMES, new Set())} />);
    expect(screen.getByRole("button", { name: "AI" }).getAttribute("aria-pressed")).toBe("true");
    const gain = screen.getByRole("region", { name: "지금 뜨는 저장소" });
    expect(gain.querySelectorAll("a.rank-row")).toHaveLength(5);
    fireEvent.click(screen.getAllByRole("button", { name: "펼치기 · 15위까지" })[0]);
    expect(gain.querySelectorAll("a.rank-row")).toHaveLength(8);       // AI 탭은 8개뿐
    fireEvent.click(screen.getByRole("button", { name: "전체" }));
    expect(gain.querySelectorAll("a.rank-row")).toHaveLength(15);
  });

  it("says when an AI tab is not classified yet", () => {
    render(<RankingSections sections={buildSections(week(), NAMES, new Set())} />);
    const fresh = screen.getByRole("region", { name: "새로 뜨는 저장소" });
    expect(fresh.textContent).toContain("아직 판정 전");
  });
});
