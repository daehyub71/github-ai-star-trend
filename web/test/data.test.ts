import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { loadBriefing, loadCard, loadCardIndex, loadIndex, loadWeek } from "@/lib/data";

import { week } from "./helpers";

let root: string;

beforeEach(() => {
  root = fs.mkdtempSync(path.join(os.tmpdir(), "startrend-web-"));
  const site = path.join(root, "site");
  fs.mkdirSync(path.join(site, "weeks"), { recursive: true });
  fs.writeFileSync(path.join(site, "index.json"), JSON.stringify({ weeks: ["2026-10-18"], latest: "2026-10-18",
    taxonomy_version: 2, types: [], categories: [{ id: "rag", name: "RAG·검색" }] }));
  fs.writeFileSync(path.join(site, "weeks", "2026-10-18.json"), JSON.stringify(week()));
});

afterEach(() => fs.rmSync(root, { recursive: true, force: true }));

describe("data", () => {
  it("reads the public site files", () => {
    const dirs = { site: path.join(root, "site"), priv: path.join(root, "private") };
    expect(loadIndex(dirs).latest).toBe("2026-10-18");
    expect(loadWeek("2026-10-18", dirs).axes.gain?.all).toHaveLength(15);
  });

  it("works without the private copy (decision 53)", () => {
    const dirs = { site: path.join(root, "site"), priv: path.join(root, "missing") };
    expect(loadCardIndex(dirs)).toEqual([]);
    expect(loadCard("o__a", dirs)).toBeNull();
    expect(loadBriefing("2026-10-18", dirs)).toBeNull();
  });

  it("reads cards and briefings from the private copy", () => {
    const priv = path.join(root, "private");
    fs.mkdirSync(path.join(priv, "cards"), { recursive: true });
    fs.mkdirSync(path.join(priv, "briefings"), { recursive: true });
    fs.writeFileSync(path.join(priv, "cards", "index.json"),
      JSON.stringify([{ repo_id: 1, full_name: "o/a", as_of: "2026-10-24", slug: "o__a" }]));
    fs.writeFileSync(path.join(priv, "cards", "o__a.md"), "# o/a\n");
    fs.writeFileSync(path.join(priv, "briefings", "2026-10-18.md"), "# brief\n");
    const dirs = { site: path.join(root, "site"), priv };
    expect(loadCardIndex(dirs)[0].slug).toBe("o__a");
    expect(loadCard("o__a", dirs)).toBe("# o/a\n");
    expect(loadBriefing("2026-10-18", dirs)).toBe("# brief\n");
  });

  it("refuses path tricks in names", () => {
    const dirs = { site: path.join(root, "site"), priv: path.join(root, "private") };
    expect(() => loadWeek("../../etc/passwd", dirs)).toThrow();
    expect(loadCard("../secret", dirs)).toBeNull();
  });
});
