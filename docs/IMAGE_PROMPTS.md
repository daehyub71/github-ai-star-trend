# 이미지 생성 프롬프트

> 디자인 시안 v1.3(2026-10-28)의 이미지 슬롯 18곳. 시안 합의 전이라 슬롯이 바뀔 수 있고, 바뀌면 이 파일도 같이 고친다.
> 시안: 디자인 캔버스 "4 · 이미지 슬롯·프롬프트" 보드.

## 쓰는 법

1. 아래 프롬프트(영어 원문)를 복사해 쓰는 이미지 생성 도구에 붙여 넣는다. 영어 원문이 결과가 가장 안정적이다.
2. 생성 도구가 준 파일(PNG 등)을 **파일 이름만 맞춰** `C:\src_new\github-ai-star-trend\web\public\art\` 에 넣는다. 확장자는 원래 형식 그대로 둬도 된다.
3. 넣은 뒤 Claude 에게 변환을 부탁한다. 원본은 `.work\art-originals\` 에 보관하고(커밋 안 됨), 사이트 폴더에는 진짜 WebP(장당 300KB 이하)만 남긴다. 다음 빌드부터 그 자리에 들어가고, 파일이 없으면 카테고리 색 그라데이션이 보인다.

크기·비율은 대략 맞으면 된다. 화면이 가장자리를 잘라 자리에 맞춘다(cover). 너무 작으면(커버 1200px, 히어로 1600px 미만 너비) 흐려 보일 수 있다.

| 넣은 날 | 파일 | 원본 | 변환 결과 |
|---|---|---|---|
| 2026-10-28 | `hero-home.webp` | PNG 1672×940 · 1.9MB | WebP 1600×900 · 83KB |
| 2026-10-28 | `hero-trends.webp` | PNG 2048×768 · 1.9MB | WebP 2048×768 · 63KB |

먼저 **1차 6장**만 만들어도 된다. 나머지는 그 카테고리 카드가 생길 때 채운다.

## 공통 규칙

- 모든 프롬프트 끝에 같은 스타일 문단이 붙어 있다. 18장이 한 세트로 보이게 하려는 것이다.
- **글자·숫자·로고·실제 브랜드·사람 얼굴 금지.** 생성 이미지의 글자는 깨지고, 실제 로고는 사칭으로 보일 수 있다. 저장소 이름은 화면이 글자로 얹는다.
- 이미지는 장식이다. 대체 텍스트는 비우고(`alt=""`), 글자 대비를 위해 위에 짙은 그라데이션을 깐다.
- 공개 리포에 커밋된다. 쓰는 생성 도구의 약관에서 공개·재배포가 되는지 확인한다. 사이트 바닥글에 "이미지는 AI 생성 일러스트"를 표기한다.
- 결과가 마음에 들지 않으면 장면 문장만 고치고 스타일 문단은 그대로 둔다.

공통 스타일 문단 (각 프롬프트에 이미 들어 있다):

```text
Style: premium 3D illustration, soft isometric perspective, glassy translucent materials with subtle emissive glow, deep navy background (#0B1020), gentle volumetric light and fine particle dust, high detail, clean minimal composition. No text, no letters, no numbers, no logos, no brand marks, no human faces.
```

## 한눈에 보기

| # | 파일 이름 | 크기 (비율) | 쓰는 곳 | 순서 |
|---|---|---|---|---|
| 1 | `hero-home.webp` | 1600×900 (16:9) | 이번 주 히어로 | 1차 |
| 2 | `hero-trends.webp` | 2400×800 (3:1) | 저장소 추이 히어로 | 1차 |
| 3 | `cat-agent-skills.webp` | 1200×675 (16:9) | 카드 커버 · 에이전트 스킬·프롬프트 | 1차 |
| 4 | `cat-coding-agent.webp` | 1200×675 (16:9) | 카드 커버 · 코딩 에이전트·IDE | 1차 |
| 5 | `cat-agent-framework.webp` | 1200×675 (16:9) | 카드 커버 · 에이전트 프레임워크 | 1차 |
| 6 | `cat-mcp-tools.webp` | 1200×675 (16:9) | 카드 커버 · MCP 서버·도구 | 1차 |
| 7 | `cat-multimodal.webp` | 1200×675 (16:9) | 카드 커버 · 멀티모달 | 2차 |
| 8 | `cat-inference.webp` | 1200×675 (16:9) | 카드 커버 · 추론·서빙 | 2차 |
| 9 | `cat-ai-apps.webp` | 1200×675 (16:9) | 카드 커버 · AI 앱·서비스 | 2차 |
| 10 | `cat-computer-use.webp` | 1200×675 (16:9) | 카드 커버 · 브라우저·컴퓨터 사용 | 2차 |
| 11 | `cat-doc-parsing.webp` | 1200×675 (16:9) | 카드 커버 · 문서·데이터 파싱 | 2차 |
| 12 | `cat-llmops.webp` | 1200×675 (16:9) | 카드 커버 · 평가·관측(LLMOps) | 2차 |
| 13 | `cat-local-llm.webp` | 1200×675 (16:9) | 카드 커버 · 로컬 LLM 실행 | 2차 |
| 14 | `cat-models.webp` | 1200×675 (16:9) | 카드 커버 · 모델·가중치 | 2차 |
| 15 | `cat-rag.webp` | 1200×675 (16:9) | 카드 커버 · RAG·검색 | 2차 |
| 16 | `cat-training.webp` | 1200×675 (16:9) | 카드 커버 · 학습·파인튜닝 | 2차 |
| 17 | `cat-vectordb-memory.webp` | 1200×675 (16:9) | 카드 커버 · 벡터DB·메모리 | 2차 |
| 18 | `cat-other-ai.webp` | 1200×675 (16:9) | 카드 커버 · 기타 AI | 2차 |

## 1차 — 먼저 만들 6장

### 1. `hero-home.webp`

- 파일: `web/public/art/hero-home.webp`
- 크기: 1600×900 (16:9) — 처음 시안은 16:10, 실제 이미지에 맞춰 16:9 로 바꿈
- 쓰는 곳: 이번 주 히어로
- 요지: 별자리처럼 이어진 빛나는 별 노드가 상승 차트처럼 솟아오름 · 파랑·보라 + 꼭대기 주황 불꽃

```text
A luminous constellation of glowing star-shaped nodes rising from lower left to upper right like a growth chart, linked by thin light trails, floating above a faint perspective grid floor; small translucent glass cubes and orbit rings drift around it; electric blue (#3B82F6) and violet (#8B5CF6) glow, with warm orange (#F97316) sparks on the highest stars. Composition: subject slightly right of center, calm darker space along the left and bottom edges. Style: premium 3D illustration, soft isometric perspective, glassy translucent materials with subtle emissive glow, deep navy background (#0B1020), gentle volumetric light and fine particle dust, high detail, clean minimal composition. No text, no letters, no numbers, no logos, no brand marks, no human faces.
```

### 2. `hero-trends.webp`

- 파일: `web/public/art/hero-trends.webp`
- 크기: 2400×800 (3:1)
- 쓰는 곳: 저장소 추이 히어로
- 요지: 어두운 공간을 가로지르는 빛의 리본 여러 줄 · 몇 줄이 꾸준히 위로 오르며 주마다 별 점 · 청록·파랑·보라

```text
Several thin glowing light ribbons flowing from left to right across a dark space; a few ribbons climb steadily higher than the rest like long-term growth curves, each marked with small bright star points at regular intervals; teal (#14B8A6), blue (#3B82F6) and violet (#8B5CF6) palette. Composition: wide panorama, the left half darker and calm for a text overlay. Style: premium 3D illustration, soft isometric perspective, glassy translucent materials with subtle emissive glow, deep navy background (#0B1020), gentle volumetric light and fine particle dust, high detail, clean minimal composition. No text, no letters, no numbers, no logos, no brand marks, no human faces.
```

### 3. `cat-agent-skills.webp`

- 파일: `web/public/art/cat-agent-skills.webp`
- 크기: 1200×675 (16:9)
- 쓰는 곳: 카드 커버 · 에이전트 스킬·프롬프트
- 요지: 유리 공구함에서 부채꼴로 펼쳐지는 스킬 카드들(렌치·방패·돋보기·붓 모양)

```text
A floating open toolbox made of frosted glass, with skill cards fanning out of it in an arc, each card carrying a different glowing tool shape (wrench, shield, magnifier, brush). Accent color violet (#8B5CF6). Composition: one subject centered, 16:9, keep the top-left corner and the bottom edge calm for small labels. Style: premium 3D illustration, soft isometric perspective, glassy translucent materials with subtle emissive glow, deep navy background (#0B1020), gentle volumetric light and fine particle dust, high detail, clean minimal composition. No text, no letters, no numbers, no logos, no brand marks, no human faces.
```

### 4. `cat-coding-agent.webp`

- 파일: `web/public/art/cat-coding-agent.webp`
- 크기: 1200×675 (16:9)
- 쓰는 곳: 카드 커버 · 코딩 에이전트·IDE
- 요지: 읽을 수 없는 빛줄 코드 편집기 창 · 아래로 갈라지고 합쳐지는 git 가지 · 빛을 쓰는 로봇 커서

```text
A floating code editor window filled with abstract glowing lines (no readable characters), several parallel branch lines splitting and merging below it like a git graph, and a small robotic cursor drawing light. Accent color blue (#3B82F6). Composition: one subject centered, 16:9, keep the top-left corner and the bottom edge calm for small labels. Style: premium 3D illustration, soft isometric perspective, glassy translucent materials with subtle emissive glow, deep navy background (#0B1020), gentle volumetric light and fine particle dust, high detail, clean minimal composition. No text, no letters, no numbers, no logos, no brand marks, no human faces.
```

### 5. `cat-agent-framework.webp`

- 파일: `web/public/art/cat-agent-framework.webp`
- 크기: 1200×675 (16:9)
- 쓰는 곳: 카드 커버 · 에이전트 프레임워크
- 요지: 가운데 지휘 구체와 궤도 위 작은 로봇 드론들 · 아래에 맞물리는 모듈 블록

```text
A central glowing orchestrator sphere linked by light beams to several small autonomous robot drones on orbital tracks, with modular puzzle-like blocks snapping together beneath them. Accent color indigo (#6366F1). Composition: one subject centered, 16:9, keep the top-left corner and the bottom edge calm for small labels. Style: premium 3D illustration, soft isometric perspective, glassy translucent materials with subtle emissive glow, deep navy background (#0B1020), gentle volumetric light and fine particle dust, high detail, clean minimal composition. No text, no letters, no numbers, no logos, no brand marks, no human faces.
```

### 6. `cat-mcp-tools.webp`

- 파일: `web/public/art/cat-mcp-tools.webp`
- 크기: 1200×675 (16:9)
- 쓰는 곳: 카드 커버 · MCP 서버·도구
- 요지: 가운데 허브 소켓에 여러 모양 플러그·케이블이 꽂힘 · 케이블 끝마다 작은 도구 블록

```text
A central hub socket with many glowing cables and plug connectors of different shapes clicking into it, each cable leading out to a small floating tool block. Accent color sky blue (#0EA5E9). Composition: one subject centered, 16:9, keep the top-left corner and the bottom edge calm for small labels. Style: premium 3D illustration, soft isometric perspective, glassy translucent materials with subtle emissive glow, deep navy background (#0B1020), gentle volumetric light and fine particle dust, high detail, clean minimal composition. No text, no letters, no numbers, no logos, no brand marks, no human faces.
```

## 2차 — 필요할 때

### 7. `cat-multimodal.webp`

- 파일: `web/public/art/cat-multimodal.webp`
- 크기: 1200×675 (16:9)
- 쓰는 곳: 카드 커버 · 멀티모달
- 요지: 음파·필름 프레임·이미지 타일 리본이 하나의 빛 줄기로 감겨 듦

```text
Interwoven ribbons of sound waveforms, film strip frames and image tiles spiraling together into one glowing stream. Accent color rose (#F43F5E). Composition: one subject centered, 16:9, keep the top-left corner and the bottom edge calm for small labels. Style: premium 3D illustration, soft isometric perspective, glassy translucent materials with subtle emissive glow, deep navy background (#0B1020), gentle volumetric light and fine particle dust, high detail, clean minimal composition. No text, no letters, no numbers, no logos, no brand marks, no human faces.
```

### 8. `cat-inference.webp`

- 파일: `web/public/art/cat-inference.webp`
- 크기: 1200×675 (16:9)
- 쓰는 곳: 카드 커버 · 추론·서빙
- 요지: 작은 서버 랙 코어에서 빛 패킷이 고속으로 쏟아져 나옴 · 잔상

```text
A compact glowing server rack core with streams of light packets rushing out at high speed, long motion trails, warm glow at the vents. Accent color orange (#F97316). Composition: one subject centered, 16:9, keep the top-left corner and the bottom edge calm for small labels. Style: premium 3D illustration, soft isometric perspective, glassy translucent materials with subtle emissive glow, deep navy background (#0B1020), gentle volumetric light and fine particle dust, high detail, clean minimal composition. No text, no letters, no numbers, no logos, no brand marks, no human faces.
```

### 9. `cat-ai-apps.webp`

- 파일: `web/public/art/cat-ai-apps.webp`
- 크기: 1200×675 (16:9)
- 쓰는 곳: 카드 커버 · AI 앱·서비스
- 요지: 떠 있는 둥근 앱 창과 휴대폰 실루엣 · 사이로 말풍선·반짝이

```text
Several floating rounded app windows and a phone silhouette made of frosted glass, with soft empty chat bubbles and sparkle particles drifting between them. Accent color pink (#EC4899). Composition: one subject centered, 16:9, keep the top-left corner and the bottom edge calm for small labels. Style: premium 3D illustration, soft isometric perspective, glassy translucent materials with subtle emissive glow, deep navy background (#0B1020), gentle volumetric light and fine particle dust, high detail, clean minimal composition. No text, no letters, no numbers, no logos, no brand marks, no human faces.
```

### 10. `cat-computer-use.webp`

- 파일: `web/public/art/cat-computer-use.webp`
- 크기: 1200×675 (16:9)
- 쓰는 곳: 카드 커버 · 브라우저·컴퓨터 사용
- 요지: 커다란 마우스 포인터와 로봇 손이 겹친 브라우저 창을 조작 · 버튼에서 클릭 물결

```text
An oversized glowing mouse pointer guided by a sleek robotic hand navigating stacked browser windows, click ripples radiating from buttons. Accent color cyan (#06B6D4). Composition: one subject centered, 16:9, keep the top-left corner and the bottom edge calm for small labels. Style: premium 3D illustration, soft isometric perspective, glassy translucent materials with subtle emissive glow, deep navy background (#0B1020), gentle volumetric light and fine particle dust, high detail, clean minimal composition. No text, no letters, no numbers, no logos, no brand marks, no human faces.
```

### 11. `cat-doc-parsing.webp`

- 파일: `web/public/art/cat-doc-parsing.webp`
- 크기: 1200×675 (16:9)
- 쓰는 곳: 카드 커버 · 문서·데이터 파싱
- 요지: 쌓인 문서·PDF 페이지가 빛줄기에 잘려 표 칸·블록으로 정리돼 떠오름

```text
Stacked paper documents and PDF-like pages being sliced by a beam of light into neat structured blocks and table cells that float upward. Accent color lime green (#84CC16). Composition: one subject centered, 16:9, keep the top-left corner and the bottom edge calm for small labels. Style: premium 3D illustration, soft isometric perspective, glassy translucent materials with subtle emissive glow, deep navy background (#0B1020), gentle volumetric light and fine particle dust, high detail, clean minimal composition. No text, no letters, no numbers, no logos, no brand marks, no human faces.
```

### 12. `cat-llmops.webp`

- 파일: `web/public/art/cat-llmops.webp`
- 크기: 1200×675 (16:9)
- 쓰는 곳: 카드 커버 · 평가·관측(LLMOps)
- 요지: 원형 게이지·선 그래프 홀로그램 대시보드 · 데이터 파이프라인을 살피는 큰 돋보기

```text
A holographic dashboard with circular gauges and line charts, and a large magnifying lens inspecting a glowing data pipeline. Accent color teal (#14B8A6). Composition: one subject centered, 16:9, keep the top-left corner and the bottom edge calm for small labels. Style: premium 3D illustration, soft isometric perspective, glassy translucent materials with subtle emissive glow, deep navy background (#0B1020), gentle volumetric light and fine particle dust, high detail, clean minimal composition. No text, no letters, no numbers, no logos, no brand marks, no human faces.
```

### 13. `cat-local-llm.webp`

- 파일: `web/public/art/cat-local-llm.webp`
- 크기: 1200×675 (16:9)
- 쓰는 곳: 카드 커버 · 로컬 LLM 실행
- 요지: 노트북 위에 떠 있는 빛나는 칩 · 노트북을 감싸는 집 모양 빛 보호막

```text
A sleek laptop with a glowing chip floating above the keyboard, surrounded by a soft house-shaped shield of light, suggesting everything runs locally. Accent color green (#22C55E). Composition: one subject centered, 16:9, keep the top-left corner and the bottom edge calm for small labels. Style: premium 3D illustration, soft isometric perspective, glassy translucent materials with subtle emissive glow, deep navy background (#0B1020), gentle volumetric light and fine particle dust, high detail, clean minimal composition. No text, no letters, no numbers, no logos, no brand marks, no human faces.
```

### 14. `cat-models.webp`

- 파일: `web/public/art/cat-models.webp`
- 크기: 1200×675 (16:9)
- 쓰는 곳: 카드 커버 · 모델·가중치
- 요지: 서로 이어진 신경망 노드로 된 큰 결정 구체 · 프리즘 빛줄기

```text
A large crystalline sphere made of interconnected neural network nodes and facets, refracting light into prism beams. Accent color purple (#A855F7). Composition: one subject centered, 16:9, keep the top-left corner and the bottom edge calm for small labels. Style: premium 3D illustration, soft isometric perspective, glassy translucent materials with subtle emissive glow, deep navy background (#0B1020), gentle volumetric light and fine particle dust, high detail, clean minimal composition. No text, no letters, no numbers, no logos, no brand marks, no human faces.
```

### 15. `cat-rag.webp`

- 파일: `web/public/art/cat-rag.webp`
- 크기: 1200×675 (16:9)
- 쓰는 곳: 카드 커버 · RAG·검색
- 요지: 빛나는 책등이 늘어선 서가 · 탐조등이 몇 권을 비추고 페이지가 답 구체로 날아감

```text
A tall library shelf of glowing blank book spines; a searchlight beam picks out a few books whose pages lift out toward a floating answer orb. Accent color golden yellow (#EAB308). Composition: one subject centered, 16:9, keep the top-left corner and the bottom edge calm for small labels. Style: premium 3D illustration, soft isometric perspective, glassy translucent materials with subtle emissive glow, deep navy background (#0B1020), gentle volumetric light and fine particle dust, high detail, clean minimal composition. No text, no letters, no numbers, no logos, no brand marks, no human faces.
```

### 16. `cat-training.webp`

- 파일: `web/public/art/cat-training.webp`
- 크기: 1200×675 (16:9)
- 쓰는 곳: 카드 커버 · 학습·파인튜닝
- 요지: 언덕·골짜기 와이어프레임 손실 지형 · 가장 낮은 골짜기로 굴러가는 빛 공

```text
A smooth 3D loss-landscape terrain of hills and valleys rendered as a glowing wireframe, with a bright ball rolling down into the lowest valley and leaving a light trail. Accent color red (#EF4444). Composition: one subject centered, 16:9, keep the top-left corner and the bottom edge calm for small labels. Style: premium 3D illustration, soft isometric perspective, glassy translucent materials with subtle emissive glow, deep navy background (#0B1020), gentle volumetric light and fine particle dust, high detail, clean minimal composition. No text, no letters, no numbers, no logos, no brand marks, no human faces.
```

### 17. `cat-vectordb-memory.webp`

- 파일: `web/public/art/cat-vectordb-memory.webp`
- 크기: 1200×675 (16:9)
- 쓰는 곳: 카드 커버 · 벡터DB·메모리
- 요지: 무리 지은 빛 점 구름 · 몇 점이 가운데 결정 메모리 코어와 가는 선으로 이어짐

```text
A 3D cloud of glowing points grouped into distinct clusters, a few points linked by thin lines to a crystal memory core in the middle. Accent color emerald (#10B981). Composition: one subject centered, 16:9, keep the top-left corner and the bottom edge calm for small labels. Style: premium 3D illustration, soft isometric perspective, glassy translucent materials with subtle emissive glow, deep navy background (#0B1020), gentle volumetric light and fine particle dust, high detail, clean minimal composition. No text, no letters, no numbers, no logos, no brand marks, no human faces.
```

### 18. `cat-other-ai.webp`

- 파일: `web/public/art/cat-other-ai.webp`
- 크기: 1200×675 (16:9)
- 쓰는 곳: 카드 커버 · 기타 AI
- 요지: 한 줄기 빛을 여러 색으로 나누는 프리즘 · 주위를 도는 작은 도형

```text
An abstract glass prism splitting a single beam of light into many colored rays, with small geometric shapes orbiting around it. Accent color slate blue (#64748B). Composition: one subject centered, 16:9, keep the top-left corner and the bottom edge calm for small labels. Style: premium 3D illustration, soft isometric perspective, glassy translucent materials with subtle emissive glow, deep navy background (#0B1020), gentle volumetric light and fine particle dust, high detail, clean minimal composition. No text, no letters, no numbers, no logos, no brand marks, no human faces.
```
