# 블라인드 30 대 Claude 초안

- 정답: 블라인드 30 — 사용자가 다른 AI 의 분류를 검토해 옮긴 라벨(FR-14.1)
- 판정: Claude 초안 `goldset_drafts.jsonl` · 판정기 `32c073201e7ecae9:claude-opus-5-5:low`
- 이번 실행 전체 비용 $1.70 (후보 200개, Batch)

정답 30개 · 답함 30개

| 지표 | 답한 것 중 | 전체 기준 |
|---|---:|---:|
| AI 여부 정확도 | 93.3% | 93.3% |
| AI 정밀도 · 재현율 | 100.0% · 89.5% | |
| 유형 정확도 (30개) | 93.3% | |
| 카테고리 정확도 (정답 AI 19개) | 63.2% | |
| 카테고리 macro-F1 | 61.7% | |
| 보정 오차(ECE) | - | |

## 카테고리별

| 카테고리 | 정답 수 | 정밀도 | 재현율 | F1 |
|---|---:|---:|---:|---:|
| MCP 서버·도구 | 5 | 100.0% | 80.0% | 88.9% |
| 기타 AI | 5 | 75.0% | 60.0% | 66.7% |
| 에이전트 스킬·프롬프트 | 2 | 100.0% | 50.0% | 66.7% |
| 멀티모달(이미지·음성·영상) | 2 | - | 0.0% | 0.0% |
| 에이전트 프레임워크 | 1 | 50.0% | 100.0% | 66.7% |
| 코딩 에이전트·IDE | 1 | 50.0% | 100.0% | 66.7% |
| 추론·서빙 | 1 | 100.0% | 100.0% | 100.0% |
| 모델·가중치 | 1 | 100.0% | 100.0% | 100.0% |
| 학습·파인튜닝 | 1 | - | 0.0% | 0.0% |

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
