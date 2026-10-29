"""시크릿 검사 (SPEC NFR-8, FR-10.3) — 압축본(archive)과 커밋 전 크기 가드가 같은 규칙을 쓴다.

알려진 토큰 모양과 실제 키 값(환경변수)을 찾는다. 찾은 **종류**만 돌려주고 값은 절대 돌려주지 않는다.
"""

import re
from collections.abc import Mapping, Sequence

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("GitHub 토큰", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b")),
    ("GitHub 세분화 토큰", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{60,}")),
    ("Anthropic 키", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("Tavily 키", re.compile(r"\btvly-[A-Za-z0-9_\-]{20,}")),
    ("Notion 토큰", re.compile(r"\b(?:ntn|secret)_[A-Za-z0-9]{40,}")),
    ("AWS 키", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("개인 키", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)
MIN_SECRET_LEN = 8                           # 너무 짧은 값은 평범한 글자와 겹친다
# 실제 값을 찾아볼 환경변수 — 이 프로젝트가 쓰는 키·토큰 전부(NFR-8)
SECRET_ENV = ("GITHUB_TOKEN", "STARTREND_GH_TOKEN", "STARTREND_ANTHROPIC_API_KEY", "STARTREND_TAVILY_API_KEY",
              "NOTION_TOKEN", "STARTREND_PRIVATE_REPO_TOKEN")


def secret_values(env: Mapping[str, str]) -> list[str]:
    return [env[k] for k in SECRET_ENV if env.get(k)]


def scan_text(text: str, *, secrets: Sequence[str]) -> list[str]:
    """찾은 시크릿의 종류 목록. 값은 돌려주지 않는다."""
    found = [name for name, rx in PATTERNS if rx.search(text)]
    if any(s and len(s) >= MIN_SECRET_LEN and s in text for s in secrets):
        found.append("실제 키 값")
    return found
