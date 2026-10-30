# 맥북으로 옮기기 — 설치·복원·확인 가이드

> 2026-10-30 작성. 윈도우 PC 에서 하던 이 프로젝트를 맥북에서 이어서 하기 위한 순서다.
> 윈도우 쪽 준비(훅 실행 권한 커밋 · `.work` 묶음 파일)는 끝났다. 키 내보내기(4-1)만 윈도우에서 한 번 하고,
> 나머지는 **맥에서 할 일**이다.

## 0. 먼저 알아 둘 것

옮길 것은 네 가지뿐이다. 나머지는 GitHub 과 클라우드에서 그대로 돌아간다.

| 무엇 | 어디에 있나 | 맥으로 옮기는 방법 |
|---|---|---|
| 소스 · 테스트 · 문서 · `data/`(52주 스타 · 랭킹 · 사이트 데이터 · 분류 결과) | 공개 저장소 | `git clone` (2단계) |
| `.work/` 일부 — Notion 대응표 · 블로그 초안과 그림 · 카드 · 유료 호출 캐시 | 윈도우 PC 에만 | 묶음 파일 풀기 (3단계) |
| 키 4개 | 윈도우 사용자 환경변수 | 암호화 파일로 내보내 맥 키체인에 등록 (4단계) |
| 워크스페이스 규칙 · Claude Code 메모리 | 윈도우 PC 에만 | 파일 복사 (5단계) |

옮기지 않아도 되는 것:

- **주간 자동 실행**(GitHub Actions, 매주 월요일 00:00 UTC) · **Vercel 사이트** · **Notion** — PC 와 상관없이 돈다.
- **비공개 저장소**(`daehyub71/github-ai-star-trend-private`) — Actions 가 매주 갱신한다. 맥에서 직접 쓸 일은 없다.

> ⚠ **`.work/notion/index.json`(Notion 대응표)이 가장 중요하다.** 이것 없이 맥에서 `notion --run` 을 하면
> Notion 데이터베이스와 페이지 50개가 중복으로 새로 만들어진다. 3단계를 끝내기 전에는 `notion --run` 을 하지 않는다.

## 1. 도구 설치

```bash
xcode-select --install                       # git 등 명령줄 도구
brew install python@3.12 node@24             # Python 은 3.12 만(pyproject: >=3.12,<3.13), Node 는 윈도우와 같은 24
brew install gh                              # 선택 — Release 올리기 등. 아래 4단계 주의 참고
```

`node@24` 가 PATH 에 잡히지 않으면 `brew info node@24` 가 알려 주는 `export PATH=…` 줄을 `~/.zshrc` 에 넣는다.

## 2. 저장소 받기와 파이썬·웹 설치

```bash
mkdir -p ~/src_new && cd ~/src_new
git clone https://github.com/daehyub71/github-ai-star-trend.git
cd github-ai-star-trend

python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt

git config core.hooksPath scripts/hooks      # 커밋 전 검사 — ruff → mypy → pytest → 크기·시크릿 가드

cd web && npm ci && cd ..
```

- `requirements-lock.txt` 는 쓰지 않는다. CI(Linux x86_64) 전용 해시 고정 파일이라 맥에서는 설치가 실패한다.
- 훅은 `.venv/bin/python` 을 자동으로 고른다. 실행 권한은 저장소에 들어 있다(100755).

## 3. `.work` 복원

윈도우에서 만든 묶음 파일 두 개를 맥으로 가져온다(AirDrop · USB · 클라우드 드라이브).

- `%USERPROFILE%\startrend-migration\startrend-work.tgz`
- `%USERPROFILE%\startrend-migration\startrend-work.tgz.sha256`

클라우드 드라이브로 옮겼다면 **실제로 내려받아졌는지**(자리표시 파일이 아닌지) 확인한 뒤 푼다.

```bash
cd ~/Downloads && shasum -a 256 -c startrend-work.tgz.sha256      # "OK" 가 나와야 한다
cd ~/src_new/github-ai-star-trend && tar -xzf ~/Downloads/startrend-work.tgz
```

묶음에 들어 있는 것:

| 폴더 | 내용 | 없으면 |
|---|---|---|
| `.work/notion/` | Notion 대응표(DB 3개 · 페이지 50개 · 업로드한 그림 ID) | **Notion 페이지가 중복 생성된다** |
| `.work/2026-10-18/` | 1회차 블로그 초안 · 사진 배치 문서 · 그림(`blog/img/` · `blog/gen/`) · 카드 · 브리핑 · 근거 | 1회차 초안을 다시 만들 수 없다 |
| `.work/site-private/` | 사이트 비공개 사본(카드·브리핑) | 웹 로컬 화면에 카드가 안 보인다 |
| `.work/cards/` | 최신 카드 보관소("다시 등장" 판단용) | 다음 주 카드가 처음부터 새로 쓰인다 |
| `.work/cache/classify` · `evidence` · `goldset` · `rank` | 유료 호출(Claude · Tavily) 응답 캐시 | 같은 작업을 다시 돌리면 다시 과금된다 |
| `.work/classify/` · `goldset-draft/` · `batches/` | 분류 판정 · 정답 세트 초안 · Batch 상태 | — |
| `.work/snapshots/` · `archive/` | 지난 주 전체 스냅샷 · 근거 압축본 | 로컬 discover 의 주간 비교 |
| `.work/art-originals/` | 카테고리 그림 원본 | — |

넣지 않은 것: GitHub API 응답 캐시(`cache/2026-10-18` 593MB · `cache/backfill-*` 14만 개 — 다시 받으면 된다,
결과는 이미 `data/` 에 있다) · 로그(`*.log`) · 시험 실행(`trial-*`) · `backfill-data/`(이미 `data/` 에 반입됨).

## 4. 키 옮기기 — 암호화 파일 → 맥 키체인

키 4개를 윈도우에서 **암호를 건 파일 하나**로 내보내고, 맥에서 풀어 키체인에 바로 넣는다. 평문 키는 양쪽 어디에도
파일로 남지 않는다(파이프로만 흐른다). 양쪽에 기본으로 있는 `openssl` 을 쓴다 — AES-256-CBC, 암호에서 키를 만드는
PBKDF2(SHA-256) 60만 회.

> 암호는 파일과 **따로** 옮긴다(외워 두기). 파일과 암호가 같은 곳(같은 메일·같은 클라우드 폴더)에 있으면 암호화한 의미가 없다.

### 4-1. 윈도우에서 내보내기 (한 번)

**Git Bash** 를 열고 그대로 붙여 넣는다. 첫 줄에서 암호를 묻는다(입력은 화면에 보이지 않는다).

```bash
cd ~/startrend-migration
read -rsp "암호(맥에서 풀 때 씀, 12자 이상): " STARTREND_PASS; echo; export STARTREND_PASS
powershell.exe -NoProfile -Command 'foreach ($n in "GITHUB_TOKEN","NOTION_TOKEN","STARTREND_ANTHROPIC_API_KEY","STARTREND_TAVILY_API_KEY") { "$n=" + [Environment]::GetEnvironmentVariable($n, "User") }' \
  | tr -d '\r' \
  | openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -md sha256 -salt -pass env:STARTREND_PASS -out startrend-keys.enc
# 확인 — 값은 보이지 않고 이름과 길이만 나온다. 4줄 모두 길이가 0 이 아니어야 한다
openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -md sha256 -pass env:STARTREND_PASS -in startrend-keys.enc \
  | awk -F= '{print $1, length($2) "자"}'
unset STARTREND_PASS
```

- 만들어지는 파일: `%USERPROFILE%\startrend-migration\startrend-keys.enc` — 묶음 파일과 함께 맥으로 가져간다.
- 어느 키가 `0자` 로 나오면 그 이름의 사용자 환경변수가 없다는 뜻이다. 윈도우 **시스템 환경 변수 편집 → 사용자 변수**를
  확인한 뒤 다시 실행한다.

### 4-2. 맥에서 풀어 키체인에 넣기

**터미널(zsh)** 에서 실행한다.

```bash
cd ~/Downloads
read -rs "STARTREND_PASS?암호: "; echo; export STARTREND_PASS
openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -md sha256 -pass env:STARTREND_PASS -in startrend-keys.enc \
  | while IFS='=' read -r n v; do
      [ -n "$v" ] && security add-generic-password -U -a "$USER" -s "$n" -w "$v" && echo "등록: $n"
    done
unset STARTREND_PASS
```

- `등록:` 줄이 4개 나오면 끝이다. 암호가 틀리면 `bad decrypt` 가 나오고 아무것도 등록되지 않는다.
- `-U` 는 같은 이름이 이미 있으면 덮어쓴다 — 키를 바꿨을 때도 같은 명령을 다시 쓰면 된다.
- 등록이 끝나면 맥에 남은 `startrend-keys.enc` 는 지워도 된다(`rm ~/Downloads/startrend-keys.enc`). 키 원본은 윈도우에 그대로 있다.
- `unknown option '-pbkdf2'` 가 나오면 맥 기본 openssl(LibreSSL)이 오래된 것이다. `brew install openssl@3` 뒤
  위 명령의 `openssl` 을 `$(brew --prefix openssl@3)/bin/openssl` 로 바꿔 실행한다.

### 4-3. 셸이 키를 읽게 하기

`~/.zshrc` 에 추가하고 터미널을 새로 연다.

```bash
for n in GITHUB_TOKEN NOTION_TOKEN STARTREND_ANTHROPIC_API_KEY STARTREND_TAVILY_API_KEY; do
  export "$n=$(security find-generic-password -a "$USER" -s "$n" -w 2>/dev/null)"
done
```

| 이름 | 쓰는 곳 |
|---|---|
| `GITHUB_TOKEN` | 공개 저장소 읽기 전용 세분화 토큰 — discover · stars · 근거 수집 |
| `NOTION_TOKEN` | Notion 연결 `github-ai-star-trend` — `notion --run` |
| `STARTREND_ANTHROPIC_API_KEY` | Console 의 github-ai-star-trend 워크스페이스 키 — 분류 · 카드 · 브리핑 · 블로그 |
| `STARTREND_TAVILY_API_KEY` | 근거 웹 검색 |

- 키 값을 채팅·문서·커밋에 붙여 넣지 않는다. 확인할 때는 길이만 본다: `echo ${#NOTION_TOKEN}`.
- **`ANTHROPIC_API_KEY` 라는 이름은 쓰지 않는다**(NFR-8). 다른 프로그램이 집어 써서 과금될 수 있다.
- `GITHUB_TOKEN` 이 설정돼 있으면 `gh` 가 로그인 대신 그 토큰(읽기 전용)을 쓴다. `gh` 로 쓰기 작업을 할 때는
  `GITHUB_TOKEN= gh release upload …` 처럼 비우고 실행한다.

## 5. 워크스페이스 규칙과 Claude Code 메모리

- 워크스페이스 공통 규칙: 윈도우 `C:\src_new\CLAUDE.md` → 맥 `~/src_new/CLAUDE.md` 로 복사한다
  (`src_new` 자체는 git 저장소가 아니다).
- Claude Code 메모리: 맥에서 `~/src_new` 를 Claude Code 로 한 번 열면 `~/.claude/projects/` 아래에 이 워크스페이스
  폴더가 생긴다. 윈도우 `%USERPROFILE%\.claude\projects\c--src-new\memory\` 의 파일(`MEMORY.md` 와 메모 파일들)을
  그 폴더의 `memory/` 에 복사한다 — "항상 한국어로 답한다" 같은 규칙이 이어진다.

## 6. 확인

```bash
cd ~/src_new/github-ai-star-trend
.venv/bin/python -m ruff check . && .venv/bin/python -m mypy startrend tests scripts && .venv/bin/python -m pytest
cd web && npm run lint && npx vitest run && npm run build && cd ..
```

| 확인 | 명령 | 기대 결과 |
|---|---|---|
| 테스트(네트워크 0 · 키 0 · 비용 0) | `pytest` | 윈도우 기준 765 통과 · 7 제외(live) |
| Notion 대응표가 넘어왔나 | `.venv/bin/python -m startrend notion --week 2026-10-18` | 계획만 — `"set_up": true` · `"create": 0` · `"blog_images": 7` |
| 블로그 초안·그림이 넘어왔나 | `.venv/bin/python -m startrend blog --week 2026-10-18 --from-draft` | 비용 0 — `"generated": 7` · `"prompts": 0` · `"excluded": 0` |
| 키가 잡히나 | `.venv/bin/python -m pytest -m live` | 실제 호출(소액 과금 가능) — 필요할 때만 |
| 웹 로컬 화면 | `cd web && npm run dev` | `http://localhost:3000` 에서 10-18 주와 카드가 보인다 |

테스트를 맥에서 돌린 적은 아직 없다. 경로·줄바꿈 차이로 실패하는 테스트가 있으면 회귀 테스트로 고친다.

## 7. 두 대를 같이 쓸 때 지킬 것

1. **작업 전에 항상 `git pull`** — 매주 월요일 Actions 가 `data/` 에 커밋을 올린다(첫 실행 2026-11-02).
2. **Notion·블로그 작업(`notion --run`, `blog`)은 한 대에서만.** 대응표가 두 대에서 따로 갈라지면 Notion 페이지가
   중복으로 생긴다. 맥으로 넘어간 뒤에는 윈도우에서 이 명령을 쓰지 않는다. 다시 돌아갈 때는 `.work/notion/index.json`
   과 그 주의 `.work/<주>/blog/` 를 함께 옮긴다. 대응표를 어디에 둘지는 미해결 결정 **D-24**(SPEC §9)다.
3. **`.work/` 는 커밋하지 않는다**(결정 59 — `.gitignore` 에 있다). 블로그 초안·그림·대응표는 공개 저장소에 올리지 않는다.
4. **저장소에 들어가는 파일명은 ASCII 만**(워크스페이스 규칙 — 맥 NFD 와 리눅스 NFC 차이). `.work/<주>/blog/gen/` 의
   한글 이름 원본 그림은 `.work` 안이라 괜찮다.

## 8. 맥에서 달라지는 것

| 윈도우 | 맥 |
|---|---|
| `.\.venv\Scripts\python.exe -m …` (문서·CLAUDE.md 의 명령) | `.venv/bin/python -m …` |
| PowerShell 로 키 읽기 `[Environment]::GetEnvironmentVariable(…,"User")` | 키체인 + `~/.zshrc` (4단계) |
| cp949 콘솔 — `PYTHONUTF8=1` · `reconfigure` 필요 | UTF-8 기본 — 필요 없음 |
| 바탕화면이 OneDrive 동기화 폴더 | 클라우드 폴더의 파일은 자리표시일 수 있다 — 열기 전에 내려받기 확인 |
