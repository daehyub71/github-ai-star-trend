// 이미지 슬롯 — web/public/art/<slot>.webp 가 있으면 그 URL, 없으면 null(화면은 카테고리 색 그라데이션)
// 빌드 때 서버 컴포넌트에서만 부른다(fs).
import fs from "node:fs";
import path from "node:path";

const SLOT = /^[a-z0-9-]+$/;

export function artDir(): string {
  return path.resolve(process.cwd(), "public", "art");
}

export function artUrl(slot: string, dir: string = artDir()): string | null {
  if (!SLOT.test(slot)) return null;
  return fs.existsSync(path.join(dir, `${slot}.webp`)) ? `/art/${slot}.webp` : null;
}
