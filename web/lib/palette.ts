// 카테고리 색 — 시안 v1.3. 칩·막대·카드 커버 그라데이션·스파크라인이 모두 이 색을 쓴다
// slot 은 카테고리 커버 이미지 이름(web/public/art/<slot>.webp, docs/IMAGE_PROMPTS.md)

export type Palette = { hue: string; dark: string; slot: string };

const COLORS: Record<string, [string, string]> = {
  "agent-framework": ["#6366F1", "#312E81"],
  "agent-skills": ["#8B5CF6", "#4C1D95"],
  "ai-apps": ["#EC4899", "#831843"],
  "coding-agent": ["#3B82F6", "#1E3A8A"],
  "computer-use": ["#06B6D4", "#164E63"],
  "doc-parsing": ["#65A30D", "#365314"],
  inference: ["#F97316", "#7C2D12"],
  llmops: ["#14B8A6", "#134E4A"],
  "local-llm": ["#22C55E", "#14532D"],
  "mcp-tools": ["#0EA5E9", "#0C4A6E"],
  models: ["#A855F7", "#581C87"],
  multimodal: ["#F43F5E", "#881337"],
  "other-ai": ["#64748B", "#1E293B"],
  rag: ["#CA8A04", "#713F12"],
  training: ["#EF4444", "#7F1D1D"],
  "vectordb-memory": ["#10B981", "#064E3B"],
};

export const CATEGORY_IDS = Object.keys(COLORS);

export function paletteOf(id: string | null | undefined): Palette {
  const key = id && id in COLORS ? id : "other-ai";
  const [hue, dark] = COLORS[key];
  return { hue, dark, slot: `cat-${key}` };
}

/** 인라인 style 로 넘기는 CSS 변수 — 색은 CSS 가 --hue/--dark 로 쓴다 */
export function hueVars(id: string | null | undefined): Record<string, string> {
  const p = paletteOf(id);
  return { "--hue": p.hue, "--dark": p.dark };
}
