// 숫자·날짜 표기 — 화면 전체가 같은 규칙을 쓴다

export function fmtInt(n: number | null | undefined): string {
  return typeof n === "number" && Number.isFinite(n) ? Math.round(n).toLocaleString("en-US") : "—";
}

export function fmtSigned(n: number | null | undefined): string {
  if (typeof n !== "number" || !Number.isFinite(n)) return "—";
  return (n >= 0 ? "+" : "−") + Math.abs(Math.round(n)).toLocaleString("en-US");
}

export function fmtPct(x: number | null | undefined, digits = 1): string {
  return typeof x === "number" && Number.isFinite(x) ? `${(x * 100).toFixed(digits)}%` : "—";
}

function parts(iso: string): [number, number, number] {
  const [y, m, d] = iso.split("-").map(Number);
  return [y, m, d];
}

/** "2026-10-18" → "10.18" */
export function mmdd(iso: string): string {
  const [, m, d] = parts(iso);
  return `${String(m).padStart(2, "0")}.${String(d).padStart(2, "0")}`;
}

/** 주 범위 — "2026년 10월 18일 – 24일", 달이 바뀌면 "2026년 10월 25일 – 11월 1일" */
export function weekRange(start: string, end: string): string {
  const [y1, m1, d1] = parts(start);
  const [y2, m2, d2] = parts(end);
  if (y1 !== y2) return `${y1}년 ${m1}월 ${d1}일 – ${y2}년 ${m2}월 ${d2}일`;
  if (m1 !== m2) return `${y1}년 ${m1}월 ${d1}일 – ${m2}월 ${d2}일`;
  return `${y1}년 ${m1}월 ${d1}일 – ${d2}일`;
}

/** 주 끝 기준 생성 30일 이내 (랭킹의 신규 축과 같은 기준 — FRESH_DAYS) */
export function isFresh(created: string, weekEnd: string): boolean {
  const days = (Date.parse(weekEnd) - Date.parse(created)) / 86_400_000;
  return days < 30;
}

export function splitName(fullName: string): { owner: string; repo: string } {
  const i = fullName.indexOf("/");
  return { owner: fullName.slice(0, i + 1), repo: fullName.slice(i + 1) };
}
