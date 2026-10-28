import type { Chip as ChipT } from "@/lib/rankings";

// 칩 색과 뜻은 시안 v1.1 그대로(DESIGN §3): 회색 카테고리 · 보라 유형 · 파랑 30일 이내 · 노랑 급등 패턴 · 점선 분류 전
export function Chip({ chip }: { chip: ChipT }) {
  return <span className={`chip chip-${chip.kind}`}>{chip.label}</span>;
}
