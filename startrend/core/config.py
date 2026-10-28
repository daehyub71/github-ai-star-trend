"""설정. 시크릿은 환경변수로만 받고 repr·로그에 남기지 않는다 (SPEC NFR-8)."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    work_dir: Path
    github_token: str | None = field(default=None, repr=False)
    anthropic_key: str | None = field(default=None, repr=False)
    tavily_key: str | None = field(default=None, repr=False)

    def require_github_token(self) -> str:
        if not self.github_token:
            raise ConfigError(
                "GITHUB_TOKEN 환경변수가 없다. 공개 저장소 읽기 전용 fine-grained 토큰을 "
                "환경변수로 설정한다 (채팅·파일에 붙여 넣지 않는다)."
            )
        return self.github_token

    def require_anthropic_key(self) -> str:
        if not self.anthropic_key:
            raise ConfigError(
                "STARTREND_ANTHROPIC_API_KEY 환경변수가 없다. Console 의 github-ai-star-trend "
                "워크스페이스 키를 사용자 환경변수로 설정한다 — ANTHROPIC_API_KEY 이름은 쓰지 않는다 (NFR-8)."
            )
        return self.anthropic_key

    def require_tavily_key(self) -> str:
        if not self.tavily_key:
            raise ConfigError(
                "STARTREND_TAVILY_API_KEY 환경변수가 없다. 근거 검색(결정 46)용 Tavily 키를 "
                "사용자 환경변수로 설정한다 (채팅·파일에 붙여 넣지 않는다)."
            )
        return self.tavily_key


def load_settings(env: Mapping[str, str] | None = None, root: Path | None = None) -> Settings:
    env = os.environ if env is None else env
    root = PROJECT_ROOT if root is None else root
    token = env.get("GITHUB_TOKEN", "").strip() or None
    # ANTHROPIC_API_KEY 는 읽지 않는다 — 다른 프로그램이 집어 써서 과금될 수 있다 (NFR-8)
    key = env.get("STARTREND_ANTHROPIC_API_KEY", "").strip() or None
    return Settings(
        data_dir=Path(env["STARTREND_DATA_DIR"]) if env.get("STARTREND_DATA_DIR") else root / "data",
        work_dir=Path(env["STARTREND_WORK_DIR"]) if env.get("STARTREND_WORK_DIR") else root / ".work",
        github_token=token,
        anthropic_key=key,
        tavily_key=env.get("STARTREND_TAVILY_API_KEY", "").strip() or None,
    )
