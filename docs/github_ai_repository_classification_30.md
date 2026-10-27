# GitHub 저장소 30개 분류 정리

작성 기준일: 2026-10-27 (한국시간)  
정리 범위: 이 대화에서 순서대로 검토한 30개 GitHub 저장소  
주의: 아래 판단은 대화 당시 확인한 README·프로젝트 설명을 바탕으로 한 **분류 기록**입니다. 일부 저장소는 접근 불가로 미확인 상태이며, 최신 변경을 일괄 재검증한 목록은 아닙니다.

## 요약

- 총 **30개**
- **AI 예: 17개** (SRS의 조건부 AI 분류 포함)
- **AI 아니요: 10개**
- **판정 보류: 3개** (내용 확인 불가)
- **유형**은 `도구/라이브러리`, `교육자료`, `모델/데이터` 등의 기존 입력 항목을 사용했습니다.
- **카테고리 없음**은 비AI 저장소로 판정한 경우이며, **미확인**은 정보 부족으로 보류한 경우입니다.

## 전체 목록

| # | 저장소 | AI 여부 | 유형 | 주 카테고리 | 보조 카테고리 | 핵심 설명 / 판단 근거 |
|---:|---|---|---|---|---|---|
| 1 | [pywinauto/pywinauto](https://github.com/pywinauto/pywinauto) | 아니요 | 도구/라이브러리 | 없음 *(유사 분야: 13)* | 없음 | Windows GUI 조작 자동화용 Python 라이브러리. AI 에이전트 자체는 아니며 13번은 기능적으로만 가장 가까움. |
| 2 | [lencx/ChatGPT](https://github.com/lencx/ChatGPT) | 예 | 도구/라이브러리 | **15. 기타 AI** | 없음 | ChatGPT를 데스크톱에서 사용하는 클라이언트 앱. 모델 개발·추론 엔진은 아님. |
| 3 | [albertan017/LLM4Decompile](https://github.com/albertan017/LLM4Decompile) | 예 | 모델/데이터 | **7. 모델·가중치** | **8. 학습·파인튜닝** | 바이너리 코드를 고수준 코드 형태로 복원하는 LLM 연구·모델 프로젝트. |
| 4 | [storytold/figcraft](https://github.com/storytold/figcraft) | 예 | 도구/라이브러리 | **3. MCP 서버·도구** | 없음 | 디자인 작업을 위한 앱·도구로 MCP 연동을 제공. |
| 5 | [microsoft/autogen](https://github.com/microsoft/autogen) | 예 | 도구/라이브러리 | **1. 에이전트 프레임워크** | 없음 | 멀티에이전트 개발·오케스트레이션 프레임워크. 검토 당시 저장소는 보관(archived)·유지보수 종료 상태로 안내됨. |
| 6 | [Panniantong/Agent-Reach](https://github.com/Panniantong/Agent-Reach) | 예 | 도구/라이브러리 | **3. MCP 서버·도구** | **9. RAG·검색** | 에이전트가 외부 정보에 접근·검색하도록 지원하는 도구·CLI. README에서 정식 MCP 서버 구현은 명확하지 않았음. |
| 7 | [nicolaslopezj/searchable](https://github.com/nicolaslopezj/searchable) | 아니요 | 도구/라이브러리 | 없음 | 없음 | Laravel 데이터베이스 검색 기능을 확장하는 일반 라이브러리. LLM/RAG 검색 아님. |
| 8 | [AppFlowy-IO/AppFlowy](https://github.com/AppFlowy-IO/AppFlowy) | 예 | 도구/라이브러리 | **15. 기타 AI** | **9. RAG·검색** | 협업·문서·지식 관리를 지원하는 워크스페이스에 AI 기능이 포함됨. |
| 9 | [CIS-C0/RFSentinel](https://github.com/CIS-C0/RFSentinel) | 아니요 | 도구/라이브러리 | 없음 | 없음 | 무선·RF/BLE/Wi-Fi 환경의 보안 감시·스캐닝 관련 도구. |
| 10 | [storytold/vectorcraft](https://github.com/storytold/vectorcraft) | 예 | 도구/라이브러리 | **3. MCP 서버·도구** | 없음 | 벡터 디자인 작업 도구이며 AI 에이전트용 MCP 인터페이스 제공. |
| 11 | [jo32/tvbox-silicon](https://github.com/jo32/tvbox-silicon) | 아니요 | 도구/라이브러리 | 없음 | 없음 | 미디어 재생을 위한 일반 애플리케이션. AI 관련 핵심 기능 확인되지 않음. |
| 12 | [alonehobo/ai-assistant-1c](https://github.com/alonehobo/ai-assistant-1c) | **미확인** | 미확인 | 미확인 | 미확인 | 검토 당시 저장소 본문에 접근하지 못해 이름만으로 분류하지 않음. |
| 13 | [Louis-CFM/coucou](https://github.com/Louis-CFM/coucou) | 예 | 도구/라이브러리 | **2. 코딩 에이전트·IDE** | 없음 | AI 코딩 에이전트 실행 상태·권한 등을 관리하고 채팅/음성 기능을 지원하는 앱. |
| 14 | [feitangyuan/onetake](https://github.com/feitangyuan/onetake) | 예 | 도구/라이브러리 | **4. 에이전트 스킬·프롬프트** | **12. 멀티모달(이미지·음성·영상)** | AI 미디어 생성 작업을 위한 스킬·워크플로 중심의 프로젝트. 검토 당시 비상업적 라이선스 조건 주의. |
| 15 | [MilaNLProc/contextualized-topic-models](https://github.com/MilaNLProc/contextualized-topic-models) | 예 | 도구/라이브러리 | **8. 학습·파인튜닝** | 없음 | BERT 등의 문맥 임베딩을 활용하는 토픽 모델링 연구·학습 라이브러리. |
| 16 | [robbietilton/Compositor](https://github.com/robbietilton/Compositor) | 아니요 | 도구/라이브러리 | 없음 | 없음 | 이미지 편집 앱. 에이전트가 파일을 수정할 수 있다는 점만으로 AI 도구로 보지 않음. |
| 17 | [apimartk5h4gmzgk/api-hub-migration-kit](https://github.com/apimartk5h4gmzgk/api-hub-migration-kit) | **미확인** | 미확인 | 미확인 | 미확인 | 저장소 내용 확인 불가. API라는 이름만으로 AI·게이트웨이 범주에 넣지 않음. |
| 18 | [eternity4719/HowToLiveBetter](https://github.com/eternity4719/HowToLiveBetter) | 예 | 교육자료 | **4. 에이전트 스킬·프롬프트** | 없음 | 생활 가이드·지식 콘텐츠가 중심이지만 Claude Code/Codex용 실제 스킬 포함. |
| 19 | [storytold/deckcraft](https://github.com/storytold/deckcraft) | 예 | 도구/라이브러리 | **3. MCP 서버·도구** | 없음 | 프레젠테이션/슬라이드 작업 앱으로 MCP 인터페이스 제공. |
| 20 | [angryip/ipscan](https://github.com/angryip/ipscan) | 아니요 | 도구/라이브러리 | 없음 | 없음 | Java 기반 IP·네트워크 스캐너. AI 기능 없음. |
| 21 | [starship/starship](https://github.com/starship/starship) | 아니요 | 도구/라이브러리 | 없음 | 없음 | 셸 터미널 프롬프트 커스터마이저. 여기서 prompt는 LLM 프롬프트가 아님. |
| 22 | [freeCodeCamp/freeCodeCamp](https://github.com/freeCodeCamp/freeCodeCamp) | 아니요 | 교육자료 | 없음 | 없음 | 범용 프로그래밍 교육 커리큘럼. 일부 AI/ML 강좌가 있어도 저장소 자체는 AI 전용이 아님. |
| 23 | [KeygraphHQ/shannon](https://github.com/KeygraphHQ/shannon) | 예 | 도구/라이브러리 | **15. 기타 AI** | 없음 | AI를 사용한 자율 웹 보안 테스트 도구. 범용 에이전트 프레임워크보다는 목적형 애플리케이션. |
| 24 | [caohoangphucs/ultraviewer-linux](https://github.com/caohoangphucs/ultraviewer-linux) | **미확인** | 미확인 | 미확인 | 미확인 | 검토 당시 접근 불가. 이름만으로 원격제어/AI 여부 판정하지 않음. |
| 25 | [apimartrkg3agz/nano-banana-reverse-api-ru](https://github.com/apimartrkg3agz/nano-banana-reverse-api-ru) | 예 | 교육자료 | **12. 멀티모달(이미지·음성·영상)** | 없음 | 제공받은 README 확인: Gemini 2.5 Flash Image(Nano Banana)를 APIMart 외부 API로 호출하는 가이드·예제·가격 정보. 독립 서버·모델 아님. |
| 26 | [nilbuild/developer-roadmap](https://github.com/nilbuild/developer-roadmap) | 아니요 | 교육자료 | 없음 | 없음 | 개발자용 학습 로드맵 전반. AI Engineer·AI Agents 등의 개별 주제가 있어도 범용 교육 저장소. |
| 27 | [deepseek-ai/DeepInfer](https://github.com/deepseek-ai/DeepInfer) | 예 | 도구/라이브러리 | **5. 추론·서빙** | 없음 | DeepSeek 모델용 고성능 추론 프레임워크. 공개본은 오프라인 추론 중심이며 완전한 온라인 서빙에는 추가 구성 필요. |
| 28 | [T-Auto/dsh-ops](https://github.com/T-Auto/dsh-ops) | 예 | 도구/라이브러리 | **3. MCP 서버·도구** | 없음 | DeepSeek Harness용 에이전트 도구 확장 플러그인. 파일/문서 처리·동적 도구 로딩·토큰 효율 향상. 독립 MCP 서버는 아님. |
| 29 | [adobe-webplatform/Snap.svg](https://github.com/adobe-webplatform/Snap.svg) | 아니요 | 도구/라이브러리 | 없음 | 없음 | 브라우저 SVG 그래픽 생성·조작·애니메이션을 위한 JavaScript 라이브러리. AI 이미지 생성 아님. |
| 30 | [ossrs/srs](https://github.com/ossrs/srs) | **예 (조건부)** | 도구/라이브러리 | **15. 기타 AI** | **4. 에이전트 스킬·프롬프트** | 본체는 일반 실시간 미디어 스트리밍 서버. 별도 AI 지원 봇·에이전트 설정·스킬·지식베이스가 있어 폭넓은 기준에서 AI 포함으로 분류. |

## 카테고리 분포 (AI로 판정한 17개 기준)

| 주 카테고리 | 개수 | 저장소 번호 |
|---|---:|---|
| 1. 에이전트 프레임워크 | 1 | 5 |
| 2. 코딩 에이전트·IDE | 1 | 13 |
| 3. MCP 서버·도구 | 5 | 4, 6, 10, 19, 28 |
| 4. 에이전트 스킬·프롬프트 | 2 | 14, 18 |
| 5. 추론·서빙 | 1 | 27 |
| 7. 모델·가중치 | 1 | 3 |
| 8. 학습·파인튜닝 | 1 | 15 |
| 12. 멀티모달(이미지·음성·영상) | 1 | 25 |
| 15. 기타 AI | 4 | 2, 8, 23, 30 |
| **합계** | **17** | |

## 판정에서 유의할 경계 사례

1. **#30 SRS:** AI 관련 스킬과 지원 봇이 실제로 있으나 제품 본체는 일반 스트리밍 서버입니다. **AI 핵심 기능만 수집**한다면 `AI 아니요`로 바꾸고, 이 문서의 AI 수는 16개·비AI 수는 11개로 조정해야 합니다.
2. **#1 pywinauto:** 데스크톱 자동화는 13번 분야와 기술적으로 유사하지만, AI 에이전트 전용 프로젝트는 아닙니다. AI 분류 대상에서는 제외했습니다.
3. **#6 Agent-Reach, #28 dsh-ops:** 3번 카테고리는 명시적으로 `에이전트가 부르는 도구·연결 모음`까지 포함하므로 적합합니다. 단, 둘을 **정식 MCP 서버라고 단정하면 안 됩니다.**
4. **#25 nano-banana-reverse-api-ru:** 사용자가 제공한 README에 따라 분류했습니다. `reverse API`라는 이름과 달리 확인된 내용은 외부 이미지 생성 API의 사용법입니다.
5. **#12, #17, #24:** 정보 미확인 3건은 추후 README 또는 소스 내용을 확보해 재분류해야 합니다.
6. **#22 freeCodeCamp, #26 developer-roadmap:** AI 교육 항목이 일부 존재한다는 이유만으로 저장소 전체를 AI 전문 프로젝트로 분류하지 않았습니다.

## 적용한 15개 카테고리 정의

| 번호 | 카테고리 | 기준 |
|---:|---|---|
| 1 | 에이전트 프레임워크 | 에이전트를 만드는 라이브러리·런타임, 오케스트레이션, 멀티에이전트 |
| 2 | 코딩 에이전트·IDE | 코드를 쓰는 에이전트, AI 코딩 CLI·IDE·확장 |
| 3 | MCP 서버·도구 | MCP 서버, 에이전트가 부르는 도구·연결 모음 |
| 4 | 에이전트 스킬·프롬프트 | 스킬·프롬프트·규칙 파일·지침 모음 |
| 5 | 추론·서빙 | 모델 추론 엔진, 서빙 서버, 가속·양자화 실행 |
| 6 | 로컬 LLM 실행 | 개인 PC·기기에서 모델을 돌리는 앱·런처 |
| 7 | 모델·가중치 | 모델 자체 — 가중치·체크포인트 공개 |
| 8 | 학습·파인튜닝 | 학습·미세조정·강화학습 프레임워크와 레시피 |
| 9 | RAG·검색 | 검색 증강 생성, 지식 검색 파이프라인 |
| 10 | 벡터DB·메모리 | 벡터 저장소, 에이전트 장기 기억 |
| 11 | 평가·관측(LLMOps) | 평가·벤치마크, 트레이싱·모니터링, 게이트웨이·라우팅 |
| 12 | 멀티모달(이미지·음성·영상) | 이미지·음성·영상 생성과 인식 |
| 13 | 브라우저·컴퓨터 사용 자동화 | 브라우저·데스크톱을 조작하는 에이전트 |
| 14 | 문서·데이터 파싱 | PDF·문서·웹 페이지를 LLM 입력으로 바꾸기 |
| 15 | 기타 AI | 위에 없는 AI 저장소 |

---

이 문서는 대화 중 개별 분류 결과를 통합한 기록입니다. 특히 이름만으로 판단하기 어려운 저장소에는 추정 분류를 추가하지 않았습니다.
