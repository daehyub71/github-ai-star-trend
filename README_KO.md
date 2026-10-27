# github-ai-star-trend

[English](README.md) | 한국어

> GitHub 의 주간 스타 변화로 **AI 트렌드 브리핑**과 **근거가 붙은 저장소 카드**를 만듭니다.
> Claude Code 와 함께 만들고 있는 개인 프로젝트이고, 아직 진행 중입니다. 설계 문서(`docs/`)는 한국어입니다.

## 왜 만들었나

AI 도구는 일주일만 지나도 새 이름이 쏟아집니다. GitHub 의 스타는 사람들의 관심이 어디로 가는지 보여 주는, 공개된 값싼 신호입니다. 이 프로젝트는 매주 어떤 저장소가 스타를 가장 많이 받았는지 재서 두 가지로 만듭니다.

1. **주간 AI 트렌드 브리핑**
2. 그 브리핑의 근거가 되는 **저장소 심층 카드** — 모든 주장에 출처 링크가 붙습니다

## 지금 상태 (2026-10-27)

| 단계 | 상태 |
|---|---|
| 0 · 골격 + 실측 | ✅ 완료 |
| 1 · 데이터 — 발굴 · 주간 스타 · 52주 소급 · 랭킹 | 🔄 진행 중 (52주 소급 실행 중) |
| 2 · 분류 — AI 인가 · 유형 · 카테고리 | 🔄 비용 없는 기초 완료, 실제 판정(과금)은 아직 |
| 3 · 근거 · 카드 · 브리핑 | 계획 |
| 4 · 화면(Next.js, Vercel 비공개 사이트) · 4b · Notion + 블로그 초안 | 시안 합의 · 계획 |
| 5 · GitHub Actions 주간 자동 실행 | 계획 |

진도율 대시보드는 [`docs/TASK.md`](docs/TASK.md) 맨 위에 있습니다.

## 어떻게 동작하나

![주간 실행 흐름](docs/img/spec-4-1-weekly-flow.png)

- **discover(발굴)** — 스타 1,000 이상인 저장소 전부(약 6만 6천 개)와 30일 안에 만들어진 새 저장소를, 검색 결과 1,000건 상한에 걸리지 않게 스타 구간으로 나눠 모읍니다. 매주 한 번 찍는 스냅샷이 약 한 시간 걸립니다.
- **stars(주간 스타)** — 이번 주와 지난 주 스냅샷을 빼서 증가 후보를 고르고, 위쪽 후보만 히스토리 API 로 요일별 정확한 값을 받습니다. 모든 저장소의 히스토리를 부르면 매주 약 13시간이 걸립니다([`docs/MEASURE.md`](docs/MEASURE.md) §2).
- **rank(랭킹)** — 네 축: 이번 주 증가, 새로 뜨는(30일 이내), 규모 대비 급성장, 누적. 하루 몰림 · 한 계정의 새 저장소 다수 · 휴면 후 폭증 같은 "확인 필요" 표시를 근거 숫자와 함께 붙입니다. **표시가 붙어도 순위에서 빼지 않습니다.**
- **classify(분류, Phase 2)** — Claude 가 정해진 형식으로 AI 여부 · 유형 · 카테고리를 답하고, 코드가 검증합니다. 틀리면 무엇이 틀렸는지 알려 주고 한 번 더 묻고, 그래도 안 되면 "미분류"로 둡니다. 랭킹 후보만, 축마다 AI 저장소 15개가 찰 때까지 판정하고, 입력이 바뀐 저장소만 다시 판정합니다.
- **evidence → analyze → brief(근거 · 카드 · 브리핑, Phase 3)** — 검색은 우리 코드가 합니다(Hacker News · 검색 API). 찾은 주소를 근거 목록으로 남기고, Claude 는 그 목록 안에서만 판정 · 요약합니다. 출처 없는 주장은 인용 게이트가 걸러 냅니다.
- **blog / notion(Phase 4b)** — 매주 초안을 Notion 에 쌓고, 사람이 검토해 직접 게시합니다. 자동 게시는 하지 않습니다.

| 짐작 대신 실측: 후보 65,922개, 하나씩 히스토리를 부르면 매주 13.2시간 | 누가 검색하나: Claude 서버 검색 대 우리 코드 |
|---|---|
| ![실측](docs/video/captures/sT1_measure.png) | ![검색 비교](docs/video/captures/sT1_search.png) |

<sub>숫자 출처: [`docs/MEASURE.md`](docs/MEASURE.md) §1–2 · §15</sub>

## 지키는 규칙

- **재기 전에 설계하지 않는다.** 설계를 바꾼 가정은 모두 비용 없이 먼저 쟀습니다([`docs/MEASURE.md`](docs/MEASURE.md)).
- **테스트를 먼저 쓴다.** 기본 테스트는 인터넷 · 키 · 돈 없이 통과합니다(테스트 중에는 네트워크 연결을 막습니다). 실제 서비스를 부르는 테스트는 `live` 로 표시해 기본 실행에서 뺍니다.
- **규칙은 사람이 아니라 코드가 지킨다.** 층 규칙 검사기(core → clients → budget → stages → cli, 단계끼리는 서로 import 하지 않음, 네트워크는 `clients/transport.py` 에서만, Anthropic SDK 는 `clients/claude.py` 에서만), 검사기가 위반을 실제로 잡는지 확인하는 통제군 테스트, 커밋 전 검사(`ruff → mypy(strict) → pytest → 크기 가드`).
- **주간 스타 파일은 한 번 쓰면 다시 쓰지 않는다.** 오래 걸리는 작업은 임시 폴더에 먼저 씁니다.
- **돈에는 안전장치를 둔다.** 과금 단계는 dry-run 이 먼저입니다. 예산 계량기는 LLM 호출 **전에** 최악의 비용을 잡아 상한(주 $10)을 넘을 수 있으면 부르지 않고, Anthropic 워크스페이스에도 월 한도를 걸었습니다.
- **외부 글은 데이터다.** README · 웹 문서 안의 문장을 지시로 다루지 않습니다.

## 시작하기

필요한 것: Python 3.12, GitHub fine-grained 토큰(공개 저장소 읽기 전용).

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt -r requirements-dev.txt   # Windows
# .venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt     # macOS / Linux
git config core.hooksPath scripts/hooks
```

환경변수 — 컴퓨터의 환경변수로만 두고 **절대 커밋하지 않습니다**(`.env` 는 gitignore):

| 변수 | 쓰는 곳 |
|---|---|
| `GITHUB_TOKEN` | discover · stars · backfill · rank |
| `STARTREND_ANTHROPIC_API_KEY` | 분류 · 카드(다음 단계). 일부러 프로젝트 전용 이름을 씁니다 — `ANTHROPIC_API_KEY` 는 다른 도구가 집어 쓸 수 있습니다 |
| `STARTREND_TAVILY_API_KEY` | 근거 검색(Phase 3) |
| `NOTION_TOKEN` | Notion 페이지(Phase 4b) |
| `STARTREND_DATA_DIR` · `STARTREND_WORK_DIR` | 선택 — `data/` · `.work/` 위치 바꾸기 |

```bash
python -m startrend contract                # GitHub API 계약 점검 (형식이 바뀌면 멈춘다)
python -m startrend discover                # 주간 스냅샷: 검색 약 1,170번 · 약 1시간 · 비용 0
python -m startrend stars                   # 이번 주 증가 (지난 주 스냅샷 필요)
python -m startrend backfill --weeks 4      # 1회성 과거 소급 (52주 ≈ 15만 번 요청)
python -m startrend rank --all              # 주간 파일이 있는 모든 주의 랭킹
python -m startrend classify --all          # dry-run: 판정 수와 비용 범위만, API 호출 0
```

```bash
python -m pytest            # 기본 게이트: 네트워크 · 키 · 비용 0
python -m pytest -m live    # 실제 API 호출 (과금될 수 있음)
```

## 폴더 구성

```
startrend/   core/(주 계산 · 입출력 · 스냅샷 · 분류 체계) · clients/(GitHub · LLM · Claude · 판정)
             stages/(discover · stars · backfill · rank · goldset · classify) · budget.py · prompts/
data/        정본 데이터 — 주간 스타 파일 · 랭킹 · 분류 체계 · 평가 세트
docs/        SPEC · PLAN · TASK · DESIGN · MEASURE, 다이어그램, 영상 자료
scripts/     다이어그램 렌더러 · 크기 가드 · 실측 스크립트 · git 훅
tests/       합성 픽스처를 쓰는 테스트
```

`.work/`(gitignore)에는 응답 캐시와 중간 파일이 쌓입니다.

## 데이터에 대해

- 스타 수와 주간 증가는 GitHub REST API 로 받아 **이 프로젝트가 계산한 값**입니다. 별을 취소한 경우나 시점 차이 때문에 github.com 에 보이는 값과 조금 다를 수 있습니다.
- "확인 필요" 표시는 휴리스틱이지 **고발이 아닙니다**.
- 이 프로젝트는 GitHub · Anthropic · Tavily · Notion 과 관계가 없습니다.

## 제작기

Claude Code 를 짝 프로그래머로 두고 만들었습니다 — 사람이 정하고, 코드가 재고, 테스트가 규칙을 지킵니다. 처음 이틀의 기록은 [`docs/video/making-of-t1.md`](docs/video/making-of-t1.md) 에 있습니다.

## 라이선스

아직 정하지 않았습니다.
