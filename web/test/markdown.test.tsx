import fs from "node:fs";
import path from "node:path";

import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Markdown } from "@/components/Markdown";

afterEach(cleanup);

// NFR-7 · 결정 43 — 카드·브리핑 마크다운은 raw HTML 을 끈 채로만 렌더한다
describe("Markdown", () => {
  it("never renders raw HTML from the text", () => {
    const { container } = render(
      <Markdown>{'안전 <script>alert(1)</script> <b>굵게</b> <img src="x" onerror="alert(1)">'}</Markdown>);
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("안전");
  });

  it("drops javascript: links and opens external links safely", () => {
    const { container } = render(
      <Markdown>{"[나쁨](javascript:alert(1)) [좋음](https://example.com/a)"}</Markdown>);
    const links = Array.from(container.querySelectorAll("a"));
    expect(links.map((a) => a.getAttribute("href"))).not.toContain("javascript:alert(1)");
    const good = links.find((a) => a.textContent === "좋음")!;
    expect(good.getAttribute("rel")).toBe("noopener noreferrer nofollow");
    expect(good.getAttribute("target")).toBe("_blank");
  });

  it("renders GFM tables", () => {
    const { container } = render(<Markdown>{"| a | b |\n|---|---|\n| 1 | 2 |"}</Markdown>);
    expect(container.querySelector("table")).not.toBeNull();
  });

  it("is the only markdown renderer and no source enables raw HTML", () => {
    const root = path.resolve(__dirname, "..");
    const files: string[] = [];
    const walk = (dir: string) => {
      for (const f of fs.readdirSync(dir, { withFileTypes: true })) {
        if (["node_modules", ".next", "test"].includes(f.name)) continue;
        const p = path.join(dir, f.name);
        if (f.isDirectory()) walk(p);
        else if (/\.(ts|tsx|mjs)$/.test(f.name)) files.push(p);
      }
    };
    walk(root);
    for (const f of files) {
      const src = fs.readFileSync(f, "utf8");
      expect(src.includes("rehype-raw"), f).toBe(false);
      expect(src.includes("dangerouslySetInnerHTML"), f).toBe(false);
      if (!f.endsWith(path.join("components", "Markdown.tsx"))) {
        expect(/from ["']react-markdown["']/.test(src), f).toBe(false);
      }
    }
  });
});
