// 카드·브리핑 마크다운 나누기 (startrend/core/cards.py 와 같은 규칙) — 렌더는 components/Markdown.tsx 만 한다

export type Front = Record<string, string>;

const CIRCLED = "①②③④⑤⑥⑦⑧";

function normalize(md: string): string {
  return md.replace(/\r\n/g, "\n");
}

/** 앞머리(--- 사이 key: value)와 나머지 */
export function splitFront(md: string): { front: Front; rest: string } {
  const text = normalize(md);
  if (!text.startsWith("---\n")) return { front: {}, rest: text };
  const end = text.indexOf("\n---\n", 4);
  if (end < 0) return { front: {}, rest: text };
  const front: Front = {};
  for (const line of text.slice(4, end).split("\n")) {
    const m = /^(\w+): (.*)$/.exec(line);
    if (m) front[m[1]] = m[2];
  }
  return { front, rest: text.slice(end + 5) };
}

function sections(rest: string): { head: string; title: string; body: string }[] {
  const out: { head: string; title: string; body: string }[] = [];
  const parts = rest.split(/^## (.+)$/m);
  for (let i = 1; i < parts.length; i += 2) out.push({ head: parts[i], title: parts[i], body: parts[i + 1] ?? "" });
  return out;
}

function intro(rest: string): { title: string; body: string } {
  const before = rest.split(/^## /m)[0];
  const m = /^# (.+)$/m.exec(before);
  const title = m ? m[1].trim() : "";
  const body = m ? before.slice(before.indexOf(m[0]) + m[0].length) : before;
  return { title, body: body.trim() };
}

export type Briefing = { front: Front; title: string; headline: string; whyNow: string[]; body: string };

export function parseBriefing(md: string): Briefing {
  const { front, rest } = splitFront(md);
  const { title, body: lead } = intro(rest);
  const why = sections(rest).find((s) => s.title.startsWith("왜 지금"));
  const whyNow = (why?.body ?? "").split("\n").filter((l) => l.startsWith("- ")).map((l) => l.slice(2).trim());
  const afterTitle = rest.slice(rest.indexOf(title) + title.length).trim();
  return { front, title, headline: lead.split("\n\n")[0]?.trim() ?? "", whyNow, body: afterTitle };
}

export type CardSection = { no: string; title: string; id: string; body: string };
export type Card = { front: Front; title: string; sections: CardSection[]; evidence: string | null };

export function parseCard(md: string): Card {
  const { front, rest } = splitFront(md);
  const { title } = intro(rest);
  const out: CardSection[] = [];
  let evidence: string | null = null;
  for (const s of sections(rest)) {
    const idx = CIRCLED.indexOf(s.head.charAt(0));
    if (idx >= 0) {
      const n = idx + 1;
      out.push({ no: String(n).padStart(2, "0"), title: s.head.slice(1).trim(), id: `s${n}`, body: s.body });
    } else if (s.head.trim() === "근거") {
      evidence = s.body.trim();
    }
  }
  return { front, title, sections: out, evidence };
}
