import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { artUrl } from "@/lib/art";
import { CATEGORY_IDS, paletteOf } from "@/lib/palette";

describe("palette", () => {
  it("gives every taxonomy category its own color and cover slot", () => {
    expect(CATEGORY_IDS).toHaveLength(16);
    const hues = new Set(CATEGORY_IDS.map((id) => paletteOf(id).hue));
    expect(hues.size).toBe(16);
    expect(paletteOf("agent-skills")).toEqual({ hue: "#8B5CF6", dark: "#4C1D95", slot: "cat-agent-skills" });
  });

  it("falls back to the other-AI color for unknown or missing categories", () => {
    expect(paletteOf(null)).toEqual(paletteOf("other-ai"));
    expect(paletteOf("no-such")).toEqual(paletteOf("other-ai"));
  });
});

describe("art", () => {
  it("returns the public URL only when the WebP file is there", () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "art-"));
    fs.writeFileSync(path.join(dir, "hero-home.webp"), "x");
    expect(artUrl("hero-home", dir)).toBe("/art/hero-home.webp");
    expect(artUrl("cat-rag", dir)).toBeNull();
  });

  it("ignores slot names that could leave the folder", () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "art-"));
    expect(artUrl("../secret", dir)).toBeNull();
    expect(artUrl("Hero Home", dir)).toBeNull();
  });
});
