# 분류 평가 — claude-draft-vs-gold200

- 정답: `goldset_classify.jsonl` (200개)
- 판정: `goldset_drafts.jsonl`

정답 200개 · 답함 200개

| 지표 | 답한 것 중 | 전체 기준 |
|---|---:|---:|
| AI 여부 정확도 | 99.0% | 99.0% |
| AI 정밀도 · 재현율 | 100.0% · 98.5% | |
| 유형 정확도 (200개) | 99.0% | |
| 카테고리 정확도 (정답 AI 130개) | 94.6% | |
| 카테고리 macro-F1 | 96.3% | |
| 보정 오차(ECE) | - | |

## 카테고리별

| 카테고리 | 정답 수 | 정밀도 | 재현율 | F1 |
|---|---:|---:|---:|---:|
| 에이전트 스킬·프롬프트 | 25 | 100.0% | 96.0% | 98.0% |
| 멀티모달(이미지·음성·영상) | 19 | 100.0% | 89.5% | 94.4% |
| 기타 AI | 19 | 94.4% | 89.5% | 91.9% |
| MCP 서버·도구 | 15 | 100.0% | 93.3% | 96.6% |
| 에이전트 프레임워크 | 11 | 91.7% | 100.0% | 95.7% |
| 평가·관측(LLMOps) | 6 | 75.0% | 100.0% | 85.7% |
| 학습·파인튜닝 | 6 | 100.0% | 83.3% | 90.9% |
| 코딩 에이전트·IDE | 5 | 83.3% | 100.0% | 90.9% |
| 추론·서빙 | 5 | 100.0% | 100.0% | 100.0% |
| 브라우저·컴퓨터 사용 자동화 | 4 | 100.0% | 100.0% | 100.0% |
| 모델·가중치 | 4 | 100.0% | 100.0% | 100.0% |
| 문서·데이터 파싱 | 3 | 100.0% | 100.0% | 100.0% |
| 로컬 LLM 실행 | 3 | 100.0% | 100.0% | 100.0% |
| RAG·검색 | 3 | 100.0% | 100.0% | 100.0% |
| 벡터DB·메모리 | 2 | 100.0% | 100.0% | 100.0% |

## 불일치 (11건)

| 저장소 | 항목 | 정답 | 판정 |
|---|---|---|---|
| ossrs/srs | is_ai | True | False |
| ossrs/srs | category | 기타 AI | (없음) |
| MilaNLProc/contextualized-topic-models | category | 학습·파인튜닝 | 기타 AI |
| eternity4719/HowToLiveBetter | is_ai | True | False |
| eternity4719/HowToLiveBetter | category | 에이전트 스킬·프롬프트 | (없음) |
| apimartrkg3agz/nano-banana-reverse-api-ru | type | 교육자료 | 기타 |
| apimartrkg3agz/nano-banana-reverse-api-ru | category | 멀티모달(이미지·음성·영상) | 평가·관측(LLMOps) |
| apimartk5h4gmzgk/api-hub-migration-kit | type | 교육자료 | 기타 |
| apimartk5h4gmzgk/api-hub-migration-kit | category | 멀티모달(이미지·음성·영상) | 평가·관측(LLMOps) |
| T-Auto/dsh-ops | category | MCP 서버·도구 | 코딩 에이전트·IDE |
| alonehobo/ai-assistant-1c | category | 기타 AI | 에이전트 프레임워크 |
