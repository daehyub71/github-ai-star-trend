// 소개·방법론 본문 — 시안 v1.4 · NFR-11("자체 산출값"과 편향을 밝힌다). 숫자는 SPEC·MEASURE 의 실측값만
// (판정 정확도 = 사람 라벨 블라인드 60, MEASURE §20 · 판정 범위 중앙값 = MEASURE §21 · 후보 수 = MEASURE §2)
import type { ReactNode } from "react";

const TOC: [string, string][] = [
  ["이 사이트는", "linear-gradient(135deg,#1F5BD8,#8B5CF6)"], ["숫자는 어떻게", "linear-gradient(135deg,#F97316,#EF4444)"],
  ["AI 저장소 판정", "linear-gradient(135deg,#8B5CF6,#EC4899)"], ["카드·브리핑", "linear-gradient(135deg,#10B981,#06B6D4)"],
  ["한계와 편향", "linear-gradient(135deg,#F59E0B,#EAB308)"], ["데이터와 코드", "linear-gradient(135deg,#64748B,#1E293B)"],
];

const AXES = [
  { name: "지금 뜨는 저장소", def: "지난 주(일~토) 받은 스타", color: "#F97316" },
  { name: "새로 뜨는 저장소", def: "생성 30일 이내 저장소 중 누적 스타 순", color: "#10B981" },
  { name: "규모 대비 급성장", def: "지난 주 증가 ÷ 주 시작 스타 — 주 시작 1,000 이상만", color: "#8B5CF6" },
  { name: "누적 스타 TOP", def: "주 마지막 시점의 총 스타 — 지난 주 대비 순위 변동", color: "#1F5BD8" },
];

const STEPS = [
  { title: "근거 모으기", text: "GitHub(README·릴리스·이슈) · Hacker News · GeekNews · 패키지 다운로드 · 웹 검색", color: "#0EA5E9" },
  { title: "AI 가 쓰기", text: "근거 번호(E1, E2…)로만 인용한다", color: "#8B5CF6" },
  { title: "인용 게이트", text: "근거 목록에 없는 링크 · 출처 없는 주장은 코드가 뺀다", color: "#EC4899" },
  { title: "숫자는 코드", text: "스타 · 증가 · 순위 · 요일별 값은 API 값으로 채운다", color: "#F97316" },
  { title: "다시 등장하면", text: "바뀐 부분만 변경 기록에 덧붙인다(LLM 호출 없음)", color: "#10B981" },
];

const LIMITS = [
  { title: "스타 ≠ 사용량", text: "스타는 관심의 신호일 뿐, 실제 사용이나 품질을 뜻하지 않습니다.", color: "#F97316" },
  { title: "생존 편향", text: "52주 소급은 지금 남아 있는 저장소만 셉니다. 그사이 지워지거나 비공개로 바뀐 저장소는 빠집니다.", color: "#EF4444" },
  { title: "가짜 스타는 \"의심\"만", text: "스타를 누른 계정은 볼 수 없어 확정할 근거가 없습니다. 하루 몰림(주간 증가의 50% 이상) · 같은 계정의 새 저장소 3개 이상 · 잠잠하다 4주 만에 10배 이상을 표시만 하고 순위에서 빼지 않습니다.", color: "#EAB308" },
  { title: "집계 범위", text: "AI 탭과 카테고리 집계는 판정된 랭킹 후보 기준입니다. 최근 주 판정 범위는 전체 증가의 약 절반(중앙값 54%)입니다.", color: "#8B5CF6" },
  { title: "AI 판정 오차", text: "카테고리 정확도 86.8% — 열에 하나꼴로 다른 카테고리일 수 있습니다.", color: "#EC4899" },
  { title: "출처의 빈칸", text: "X(트위터)와 Reddit 은 본문을 읽지 않고, 검색 결과에 나온 링크와 짧은 요약만 남깁니다.", color: "#64748B" },
];

function Head({ no, children }: { no: number; children: ReactNode }) {
  return (
    <h2>
      <span className="sec-badge" style={{ background: TOC[no - 1][1] }}>{String(no).padStart(2, "0")}</span>
      {children}
    </h2>
  );
}

export function AboutContent() {
  return (
    <div className="about-layout">
      <nav aria-label="이 페이지 목차" className="panel about-toc">
        <strong>목차</strong>
        {TOC.map(([label, bg], i) => (
          <a key={label} href={`#s${i + 1}`}>
            <span className="toc-no" style={{ background: bg }}>{String(i + 1).padStart(2, "0")}</span>{label}
          </a>
        ))}
      </nav>

      <div className="about-main">
        <section id="s1" className="panel about-sec lift">
          <Head no={1}>이 사이트는</Head>
          <p className="lead">매주 월요일 09:00 KST 에 지난 주(UTC 일요일~토요일)를 정리합니다. 만드는 것은 세 가지입니다.</p>
          <div className="trio">
            <div className="t-orange"><b>4축 랭킹</b><span>지금 뜨는 · 새로 뜨는 · 규모 대비 급성장 · 누적 TOP — 전체 탭과 AI 탭</span></div>
            <div className="t-violet"><b>저장소 카드</b><span>AI 탭 저장소마다 — 왜 지금 떴나, 무엇인가, 비교, 활용사례, 한계</span></div>
            <div className="t-cyan"><b>브리핑 · 추이</b><span>주간 브리핑 1편과 꾸준히 뜨는 저장소 목록(12·52주)</span></div>
          </div>
          <p className="muted">Claude Code 와 함께 만드는 개인 프로젝트입니다. 검색엔진에는 노출하지 않습니다.</p>
        </section>

        <section id="s2" className="panel about-sec">
          <Head no={2}>숫자는 어떻게</Head>
          <div className="table-wrap">
            <table style={{ minWidth: 520 }}>
              <thead><tr><th scope="col">축</th><th scope="col">무엇을 재나</th></tr></thead>
              <tbody>
                {AXES.map((a) => (
                  <tr key={a.name}>
                    <th scope="row" style={{ whiteSpace: "nowrap" }}><span className="sw-dot" style={{ background: a.color }} />{a.name}</th>
                    <td>{a.def}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="bullets">
            <li><b>후보</b> — 스타 1,000 이상 저장소 전체(약 6.6만 개)를 매주 스냅샷하고, 생성 30일 이내 새 저장소를 따로 찾습니다. 지난 주 스냅샷과의 차이로 후보를 고르고, 화면에 나갈 저장소는 GitHub 히스토리 API 로 정확한 주간 값과 요일별 값을 받습니다.</li>
            <li><b>표</b> — 축마다 15개, 화면에는 5개(펼치면 15개). 같은 입력이면 같은 결과가 나옵니다.</li>
            <li><b>저장소 추이</b> — AI 탭의 뜨는 축(지금 뜨는 · 새로 뜨는 · 규모 대비 급성장)에 든 주를 셉니다. 누적 TOP 은 큰 저장소가 매주 끼어 빼고 셉니다.</li>
          </ul>
          <p className="banner"><b>자체 산출값입니다.</b> GitHub 의 공식 지표가 아니며, GitHub 가 계산하는 Trending 과도 다릅니다.</p>
        </section>

        <section id="s3" className="panel about-sec">
          <Head no={3}>AI 저장소 판정</Head>
          <p className="lead">Claude(Opus 5.5)가 저장소 설명·토픽·README 앞부분을 읽고 <b>AI 여부 · 유형 · 카테고리(16개)</b>를 정합니다.</p>
          <div className="duo">
            <div><b>AI 로 보는 것 (넓게)</b>AI 모델·에이전트를 만들거나 · 돌리거나 · 평가하거나 · 쓰는 저장소. AI 기능을 내세우거나 MCP 같은 에이전트 연결을 주는 앱도 AI 입니다.</div>
            <div><b>AI 로 보지 않는 것</b>에이전트가 다룰 수 있을 뿐인 일반 앱, AI 강좌가 일부 있는 범용 교육자료.</div>
          </div>
          <div className="acc">
            <div><span>96.7%</span><small>AI 여부</small></div>
            <div><span>98.3%</span><small>유형</small></div>
            <div><span>86.8%</span><small>카테고리(16개)</small></div>
          </div>
          <p className="muted">정확도는 사람이 먼저 라벨한 블라인드 60개 기준입니다. 같은 입력이라도 판정이 1~2건씩 흔들릴 수 있습니다. 판정은 <b>랭킹 후보만</b> 합니다(축마다 AI 저장소 15개가 찰 때까지 위에서부터) — 그래서 카테고리 집계는 판정된 저장소 기준이고, 작은 저장소의 긴 꼬리는 빠집니다(최근 주 판정 범위 중앙값 약 54%).</p>
        </section>

        <section id="s4" className="panel about-sec">
          <Head no={4}>카드·브리핑은 이렇게 씁니다<span className="ai-badge after">AI 작성</span></Head>
          <ol className="steps">
            {STEPS.map((s, i) => (
              <li key={s.title} style={{ borderTopColor: s.color }}>
                <span className="mono" style={{ color: s.color }}>{String(i + 1).padStart(2, "0")}</span>
                <b>{s.title}</b>
                <span>{s.text}</span>
              </li>
            ))}
          </ol>
          <ul className="bullets">
            <li><b>사람이 검토하지 않습니다.</b> 주장마다 출처 링크와 <b>확인</b>(출처가 직접 말함) · <b>추정</b>(해석) 표시를 붙입니다.</li>
            <li>Reddit·X 는 검색 결과에 나온 링크와 짧은 요약만 남기고 본문은 읽지 않습니다. 근거 목록의 제목은 120자까지만 보여 줍니다.</li>
            <li>외부 글(README·웹 글) 안의 문장은 지시로 따르지 않습니다 — 데이터로만 다룹니다.</li>
          </ul>
        </section>

        <section id="s5" className="panel about-sec">
          <Head no={5}>한계와 편향</Head>
          <div className="limits">
            {LIMITS.map((l) => (
              <div key={l.title} style={{ borderLeftColor: l.color }}><b>{l.title}</b><span>{l.text}</span></div>
            ))}
          </div>
        </section>

        <section id="s6" className="panel about-sec">
          <Head no={6}>데이터와 코드</Head>
          <dl className="facts wide">
            <dt>코드·데이터</dt>
            <dd><a href="https://github.com/daehyub71/github-ai-star-trend" target="_blank" rel="noopener noreferrer">github.com/daehyub71/github-ai-star-trend</a> — 주간 스타 파일·랭킹·분류 결과가 평문(CSV·JSON)으로 쌓입니다.</dd>
            <dt>카드·브리핑</dt><dd>공개 저장소에는 두지 않고 이 사이트에서만 보여 줍니다.</dd>
            <dt>출처</dt><dd>GitHub API · Hacker News(Algolia) · GeekNews · PyPI·npm 다운로드 · ecosyste.ms(CC BY-SA 4.0) · 웹 검색(Tavily)</dd>
            <dt>이미지</dt><dd>AI 생성 일러스트입니다.</dd>
          </dl>
        </section>
      </div>
    </div>
  );
}
