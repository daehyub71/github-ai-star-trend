// 빌드 때 서버 컴포넌트에서만 읽는다(NFR-6) — 클라이언트 컴포넌트에서 import 하지 않는다.
// 공개 데이터는 ../data/site (FR-9), 카드·브리핑은 공개 저장소 밖 비공개 사본(결정 53, 자리는 Phase 5).
import fs from "node:fs";
import path from "node:path";

import type { Categories, CardRef, RepoTrends, SiteIndex, WeekData } from "./types";

export type Dirs = { site: string; priv: string };

export function defaultDirs(): Dirs {
  return {
    site: process.env.STARTREND_SITE_DIR ?? path.resolve(process.cwd(), "..", "data", "site"),
    priv: process.env.STARTREND_PRIVATE_DIR ?? path.resolve(process.cwd(), "..", ".work", "site-private"),
  };
}

const WEEK = /^\d{4}-\d{2}-\d{2}$/;
const SLUG = /^[A-Za-z0-9._-]+__[A-Za-z0-9._-]+$/;

function readJson<T>(file: string): T {
  return JSON.parse(fs.readFileSync(file, "utf8")) as T;
}

function readIf(file: string): string | null {
  return fs.existsSync(file) ? fs.readFileSync(file, "utf8") : null;
}

export function loadIndex(dirs: Dirs = defaultDirs()): SiteIndex {
  return readJson<SiteIndex>(path.join(dirs.site, "index.json"));
}

export function loadWeek(week: string, dirs: Dirs = defaultDirs()): WeekData {
  if (!WEEK.test(week)) throw new Error(`주 이름이 아니다: ${week}`);
  return readJson<WeekData>(path.join(dirs.site, "weeks", `${week}.json`));
}

export function loadCategories(dirs: Dirs = defaultDirs()): Categories {
  return readJson<Categories>(path.join(dirs.site, "categories.json"));
}

export function loadRepos(dirs: Dirs = defaultDirs()): RepoTrends {
  const file = path.join(dirs.site, "repos.json");
  return fs.existsSync(file) ? readJson<RepoTrends>(file) : { weeks: [], axes: [], repos: [] };
}

export function loadCardIndex(dirs: Dirs = defaultDirs()): CardRef[] {
  const file = path.join(dirs.priv, "cards", "index.json");
  return fs.existsSync(file) ? readJson<CardRef[]>(file).filter((c) => SLUG.test(c.slug)) : [];
}

export function loadCard(slug: string, dirs: Dirs = defaultDirs()): string | null {
  return SLUG.test(slug) ? readIf(path.join(dirs.priv, "cards", `${slug}.md`)) : null;
}

export function loadBriefing(week: string, dirs: Dirs = defaultDirs()): string | null {
  return WEEK.test(week) ? readIf(path.join(dirs.priv, "briefings", `${week}.md`)) : null;
}

export function briefingWeeks(dirs: Dirs = defaultDirs()): string[] {
  const dir = path.join(dirs.priv, "briefings");
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir).filter((f) => WEEK.test(f.replace(/\.md$/, ""))).map((f) => f.replace(/\.md$/, ""));
}
