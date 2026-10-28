// 저장소 카드 — 시안 v1.1: 8개 섹션 + 옆 목차 · 근거와 인용 게이트 상자
// 카드 본문(LLM 글 + 코드 표)은 비공개 사본에서, ② 의 지표 타일·막대는 공개 주간 데이터에서 읽는다
import Link from "next/link";

import { loadIndex, loadWeek } from "@/lib/data";
import { fmtInt, fmtPct, fmtSigned, mmdd, splitName } from "@/lib/format";
import { parseCard } from "@/lib/markdown";
import type { Entry } from "@/lib/types";

import { Chip } from "./Chip";
import { Markdown } from "./Markdown";
import { SiteFooter, SiteHeader } from "./SiteHeader";

const DAY = ["일", "월", "화", "수", "목", "금", "토"];

function findEntry(week: string | undefined, fullName: string): Entry | null {
  if (!week || !loadIndex().weeks.includes(week)) return null;
  const data = loadWeek(week);
  for (const tabs of Object.values(data.axes)) {
    for (const e of [...(tabs?.ai ?? []), ...(tabs?.all ?? [])]) {
      if (e.full_name.toLowerCase() === fullName.toLowerCase()) return e;
    }
  }
  return null;
}

function Bars({ values, labels, focusLast, caption }: { values: number[]; labels: [string, string];
  focusLast?: boolean; caption: string }) {
  const max = Math.max(1, ...values);
  return (
    <figure style={{ margin: 0, display: "flex", flexDirection: "column", gap: 6, flex: "1 1 260px", minWidth: 0 }}>
      <figcaption className="muted small">{caption}</figcaption>
      <div className="bars" role="img" aria-label={`${caption}: ${values.map(fmtInt).join(", ")}`}>
        {values.map((v, i) => (
          <div key={i} className={`b${focusLast && i === values.length - 1 ? " focus" : ""}`}
            style={{ height: `${Math.max(2, Math.round((v / max) * 116))}px` }} title={fmtInt(v)} />
        ))}
      </div>
      <div className="bar-labels"><span>{labels[0]}</span><span>{labels[1]}</span></div>
    </figure>
  );
}

function Numbers({ e, asOf, week }: { e: Entry; asOf: string; week: string }) {
  const prevWeek = e.spark.length > 1 ? e.spark[e.spark.length - 2] : null;
  const kpis = [
    { label: "누적 스타", value: fmtInt(e.stars_end), sub: asOf, up: false },
    { label: "지난 주", value: fmtSigned(e.gain), sub: prevWeek ? `전주 ${fmtInt(prevWeek)}` : "전주 —", up: true },
    { label: "규모 대비 성장률", value: fmtPct(e.growth), sub: `주 시작 ${fmtInt(e.start_stars)}`, up: true },
    { label: "생성", value: mmdd(e.created), sub: e.created.slice(0, 4) + "년", up: false },
  ];
  return (
    <>
      <div className="kpis">
        {kpis.map((k) => (
          <div className="kpi" key={k.label}>
            <span className="label">{k.label}</span>
            <span className={`v${k.up ? " up" : ""}`}>{k.value}</span>
            <span className="sub">{k.sub}</span>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 20 }}>
        <Bars values={e.spark} labels={["12주 전", `${mmdd(week)} 주`]} focusLast caption="주간 스타 · 최근 12주" />
        {e.days ? <Bars values={e.days} labels={[`${DAY[0]} ${mmdd(week)}`, DAY[6]]} caption="이번 주 일별 스타 (UTC)" /> : null}
      </div>
    </>
  );
}

export function CardView({ markdown, fullName }: { markdown: string; fullName: string }) {
  const card = parseCard(markdown);
  const f = card.front;
  const entry = findEntry(f.week, fullName);
  const { owner, repo } = splitName(fullName);
  const names = Object.fromEntries(loadIndex().categories.map((c) => [c.id, c.name]));
  const [prompt, model, effort] = (f.fingerprint ?? "").split(":");

  return (
    <>
      <SiteHeader current="card" />
      <main className="page">
        <nav aria-label="위치" className="crumbs">
          <Link href={f.week ? `/week/${f.week}` : "/"}>{f.week ? `${f.week} 주` : "이번 주"}</Link> › 저장소 카드
        </nav>
        <section className="panel" style={{ flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between", gap: "12px 24px" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, minWidth: 0, flex: "999 1 420px" }}>
            <h1 className="card-title"><span className="owner">{owner}</span>{repo}</h1>
            {entry?.description ? <p style={{ margin: 0, fontSize: 15, lineHeight: 1.7, color: "var(--text-2)" }}>{entry.description}</p> : null}
            <div className="chips">
              {entry?.category ? <Chip chip={{ kind: "cat", label: names[entry.category] ?? entry.category }} /> : null}
              {entry?.type ? <Chip chip={{ kind: "type", label: entry.type }} /> : null}
              {entry?.language ? <Chip chip={{ kind: "no", label: entry.language }} /> : null}
              {(entry?.flags ?? []).map((fl) => <Chip key={fl.kind} chip={{ kind: "flag", label: fl.label }} />)}
            </div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, flex: "1 1 220px" }}>
            <a className="btn" href={`https://github.com/${fullName}`} target="_blank" rel="noopener noreferrer"
              style={{ fontWeight: 600, alignSelf: "flex-start" }}>GitHub 에서 보기 ↗</a>
            <span className="muted small" style={{ lineHeight: 1.6 }}>
              카드 기준일 {f.as_of ?? "—"} · 처음 작성 {f.generated ?? "—"}{f.updated ? ` · 갱신 ${f.updated}` : ""}
            </span>
          </div>
        </section>

        <div className="card-layout">
          <div className="card-main">
            {card.sections.map((s) => (
              <section key={s.id} id={s.id} className="panel">
                <h2><span className="sec-no">{s.no}</span>{s.title}</h2>
                {s.id === "s2" && entry && f.week ? <Numbers e={entry} asOf={f.as_of ?? ""} week={f.week} /> : null}
                <Markdown>{s.body}</Markdown>
              </section>
            ))}
            {card.evidence ? (
              <section id="evidence" className="panel">
                <h2>근거</h2>
                <Markdown>{card.evidence}</Markdown>
              </section>
            ) : null}
          </div>
          <aside className="card-aside">
            <nav aria-label="카드 목차" className="panel toc" style={{ gap: 2, padding: 16 }}>
              <strong style={{ fontSize: 13, padding: "0 8px 6px" }}>목차</strong>
              {card.sections.map((s) => (
                <a key={s.id} href={`#${s.id}`}><span className="mono small" style={{ color: "var(--muted)" }}>{s.no}</span>{s.title}</a>
              ))}
              {card.evidence ? <a href="#evidence"><span className="mono small" style={{ color: "var(--muted)" }}>··</span>근거</a> : null}
            </nav>
            <div className="panel" style={{ padding: 16, gap: 10 }}>
              <strong style={{ fontSize: 13 }}>근거와 인용 게이트</strong>
              <dl className="facts">
                <dt>모은 근거</dt><dd>{f.evidence ?? "—"}</dd>
                <dt>검사한 블록</dt><dd>{f.gate_checked ?? "—"}</dd>
                <dt>출처 없어 제외</dt><dd>{f.gate_excluded ?? "—"}</dd>
              </dl>
              <span className="muted small" style={{ lineHeight: 1.6 }}>
                출처는 근거 번호로만 받고 링크는 코드가 만든다 · 모델 {model ?? "—"} · effort {effort ?? "—"} · 지시문 {prompt ? prompt.slice(0, 8) : "—"}
              </span>
            </div>
          </aside>
        </div>
        <SiteFooter asOf={f.as_of} />
      </main>
    </>
  );
}
