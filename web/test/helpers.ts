import type { Entry, WeekData } from "@/lib/types";

export function entry(id: number, fullName: string, over: Partial<Entry> = {}): Entry {
  return {
    id, full_name: fullName, description: `${fullName} desc`, language: "Python", created: "2025-01-01",
    stars_end: 10_000 + id, gain: 5_000 - id, growth: 0.25, start_stars: 8_000, rank: id, prev_rank: null,
    is_ai: true, type: "도구/라이브러리", category: "rag", secondary: null, flags: [], exact: true,
    days: [1, 2, 3, 4, 5, 6, 7], spark: Array.from({ length: 12 }, (_, i) => i * 10), ...over,
  };
}

export function week(n = 15): WeekData {
  // 축마다 새 배열 — 한 축을 고친 테스트가 다른 축에 번지지 않게
  const all = () => Array.from({ length: n }, (_, i) => entry(i + 1, `o/r${i + 1}`));
  const ai = () => all().filter((e) => e.id % 2 === 1).map((e, i) => ({ ...e, rank: i + 1 }));
  return {
    week: "2026-10-18", week_end: "2026-10-24",
    axes: {
      gain: { all: all(), ai: ai() },
      fresh: { all: all().slice(0, 3).map((e) => ({ ...e, created: "2026-10-10" })), ai: null },
      growth: { all: all(), ai: ai() },
      total: { all: all(), ai: ai() },
    },
    ai_status: { gain: { found: ai.length, pending_above: 0 } },
  };
}

export const NAMES: Record<string, string> = { rag: "RAG·검색", "mcp-tools": "MCP 서버·도구" };
