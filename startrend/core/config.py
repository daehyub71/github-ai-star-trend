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

    def require_github_token(self) -> str:
        if not self.github_token:
            raise ConfigError(
                "GITHUB_TOKEN 환경변수가 없다. 공개 저장소 읽기 전용 fine-grained 토큰을 "
                "환경변수로 설정한다 (채팅·파일에 붙여 넣지 않는다)."
            )
        return self.github_token


def load_settings(env: Mapping[str, str] | None = None, root: Path | None = None) -> Settings:
    env = os.environ if env is None else env
    root = PROJECT_ROOT if root is None else root
    token = env.get("GITHUB_TOKEN", "").strip() or None
    return Settings(
        data_dir=Path(env["STARTREND_DATA_DIR"]) if env.get("STARTREND_DATA_DIR") else root / "data",
        work_dir=Path(env["STARTREND_WORK_DIR"]) if env.get("STARTREND_WORK_DIR") else root / ".work",
        github_token=token,
    )
