import type { CSSProperties } from "react";

import { hueVars } from "@/lib/palette";
import type { Chip as ChipT } from "@/lib/rankings";

// 칩 뜻은 시안 v1.1 그대로(DESIGN §3). v1.3: 카테고리는 카테고리 색, 카드가 있으면 '카드' 배지
export function Chip({ chip }: { chip: ChipT }) {
  const style = chip.kind === "cat" && chip.catId ? (hueVars(chip.catId) as CSSProperties) : undefined;
  return <span className={`chip chip-${chip.kind}`} style={style}>{chip.label}</span>;
}
