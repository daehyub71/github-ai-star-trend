# 블라인드 전체 대 Claude 판정

- 정답: `goldset_classify.jsonl` 의 블라인드 행 — 초안 없이 사용자가 라벨(FR-14.1)
- 판정: Claude `drafts_v2_blind60.jsonl` · 판정기 `0c9892c3deabdd84:claude-opus-5-5:low`
- 이번 실행 비용 $1.11 (후보 60개, 일반 호출)

정답 60개 · 답함 60개

| 지표 | 답한 것 중 | 전체 기준 |
|---|---:|---:|
| AI 여부 정확도 | 98.3% | 98.3% |
| AI 정밀도 · 재현율 | 100.0% · 97.4% | |
| 유형 정확도 (60개) | 98.3% | |
| 카테고리 정확도 (정답 AI 38개) | 73.7% | |
| 카테고리 macro-F1 | 67.5% | |
| 보정 오차(ECE) | - | |

## 카테고리별

| 카테고리 | 정답 수 | 정밀도 | 재현율 | F1 |
|---|---:|---:|---:|---:|
| 에이전트 스킬·프롬프트 | 8 | 100.0% | 100.0% | 100.0% |
| MCP 서버·도구 | 6 | 100.0% | 66.7% | 80.0% |
| AI 앱·서비스 | 5 | 36.4% | 80.0% | 50.0% |
| 기타 AI | 5 | 0.0% | 0.0% | 0.0% |
| 평가·관측(LLMOps) | 4 | 100.0% | 100.0% | 100.0% |
| 모델·가중치 | 3 | 100.0% | 100.0% | 100.0% |
| 멀티모달(이미지·음성·영상) | 2 | 66.7% | 100.0% | 80.0% |
| 에이전트 프레임워크 | 1 | 100.0% | 100.0% | 100.0% |
| 코딩 에이전트·IDE | 1 | - | 0.0% | 0.0% |
| 브라우저·컴퓨터 사용 자동화 | 1 | 100.0% | 100.0% | 100.0% |
| 추론·서빙 | 1 | 100.0% | 100.0% | 100.0% |
| 학습·파인튜닝 | 1 | - | 0.0% | 0.0% |

## 불일치 (12건)

| 저장소 | 항목 | 정답 | 판정 |
|---|---|---|---|
| home-assistant/core | is_ai | True | False |
| home-assistant/core | category | 기타 AI | (없음) |
| ossrs/srs | category | AI 앱·서비스 | 멀티모달(이미지·음성·영상) |
| MilaNLProc/contextualized-topic-models | category | 학습·파인튜닝 | 기타 AI |
| nocobase/nocobase | category | 기타 AI | AI 앱·서비스 |
| ZhuLinsen/daily_stock_analysis | category | 기타 AI | AI 앱·서비스 |
| BuilderPulse/BuilderPulse | type | 큐레이션 목록 | 기타 |
| BuilderPulse/BuilderPulse | category | 기타 AI | AI 앱·서비스 |
| Louis-CFM/coucou | category | 코딩 에이전트·IDE | AI 앱·서비스 |
| storytold/deckcraft | category | MCP 서버·도구 | AI 앱·서비스 |
| storytold/figcraft | category | MCP 서버·도구 | AI 앱·서비스 |
| YOURSJEYO/claude-switcher | category | 기타 AI | AI 앱·서비스 |

## 묶음별

| 정답 묶음 | 정답 수 | AI 여부 정확도 | 유형 정확도 | 카테고리 정확도 | 카테고리 macro-F1 |
|---|---:|---:|---:|---:|---:|
| 블라인드 전체 | 60 | 98.3% | 98.3% | 73.7% | 67.5% |
| 1차 30 — 규칙을 만들 때 본 것 | 30 | 100.0% | 100.0% | 73.7% | 69.1% |
| 2차 30 — 처음 보는 것 | 30 | 96.7% | 96.7% | 73.7% | 83.3% |
