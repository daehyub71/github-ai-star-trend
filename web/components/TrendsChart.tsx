"use client";

// 카테고리 추이 그래프 — 시안 v1.1: 카테고리 고르기(ALL 포함 최대 6개) · 12주/52주 · 선 그래프 (결정 43: 차트 라이브러리)
import { useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { fmtInt } from "@/lib/format";
import { chartData, MAX_SELECTED, PERIODS } from "@/lib/trends";
import type { Categories } from "@/lib/types";

const PALETTE = ["#1F5BD8", "#B4441B", "#0F766E", "#7C3AED", "#A16207"];
const ALL_COLOR = "#15181E";

export function TrendsChart({ cats, initial }: { cats: Categories; initial: string[] }) {
  const [selected, setSelected] = useState<string[]>(initial);
  const [period, setPeriod] = useState<number>(12);
  const ids = ["ALL", ...Object.keys(cats.series).filter((k) => k !== "ALL")];
  const others = selected.filter((s) => s !== "ALL");
  const color = (id: string) => (id === "ALL" ? ALL_COLOR : PALETTE[others.indexOf(id) % PALETTE.length]);
  const data = chartData(cats, selected, period);      // 최대 6계열 × 52주 — 매번 계산해도 가볍다
  const full = selected.length >= MAX_SELECTED;
  const toggle = (id: string) =>
    setSelected(selected.includes(id) ? selected.filter((s) => s !== id) : [...selected, id]);

  return (
    <section className="panel">
      <div className="panel-head">
        <strong style={{ fontSize: 13 }}>카테고리 고르기 · ALL 포함 최대 {MAX_SELECTED}개</strong>
        <div role="group" aria-label="기간" className="seg">
          {PERIODS.map((p) => (
            <button key={p} type="button" aria-pressed={period === p} onClick={() => setPeriod(p)}>{p}주</button>
          ))}
        </div>
      </div>
      <div role="group" aria-label="카테고리" style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {ids.map((id) => {
          const on = selected.includes(id);
          return (
            <button key={id} type="button" className="chip-btn" aria-pressed={on} disabled={!on && full}
              onClick={() => toggle(id)}>
              <span className="dot" aria-hidden="true" style={{ background: on ? (id === "ALL" ? "#fff" : color(id)) : "#C3C9D3" }} />
              {cats.names[id] ?? id}
            </button>
          );
        })}
      </div>
      <figure style={{ margin: 0, display: "flex", flexDirection: "column", gap: 8 }}>
        <figcaption className="muted small">세로축: 주간 스타 증가 합계 · 가로축: 주 시작일(UTC)</figcaption>
        <div style={{ width: "100%", height: 300 }} role="img"
          aria-label={`카테고리별 주간 스타 증가, 최근 ${period}주: ${selected.map((s) => cats.names[s] ?? s).join(", ")}`}>
          <ResponsiveContainer>
            <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 8 }}>
              <CartesianGrid stroke="#EEF0F3" vertical={false} />
              <XAxis dataKey="week" tick={{ fontSize: 11, fill: "#6B7280" }} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: "#6B7280" }} tickFormatter={(v: number) => fmtInt(v)} width={64} />
              <Tooltip formatter={(v) => fmtInt(typeof v === "number" ? v : Number(v))} />
              {selected.map((id) => (
                <Line key={id} type="monotone" dataKey={id} name={cats.names[id] ?? id} stroke={color(id)}
                  strokeWidth={id === "ALL" ? 3 : 2.5} dot={false} connectNulls={false} isAnimationActive={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
        <ul className="legend">
          {selected.map((id) => (
            <li key={id}><span className="swatch" style={{ background: color(id) }} aria-hidden="true" />
              {id === "ALL" ? "ALL (모든 AI 카테고리 합계)" : cats.names[id] ?? id}</li>
          ))}
        </ul>
      </figure>
    </section>
  );
}
