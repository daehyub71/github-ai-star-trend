"""콘텐츠 해시. 정체성과 증분 판단의 기준이다 (워크스페이스 원칙 5)."""

import hashlib
import json
from typing import Any


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def content_hash(obj: Any) -> str:
    """JSON 으로 표현 가능한 값의 해시. 키 순서와 무관하다."""
    canonical = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_text(canonical)


def short_hash(text: str) -> str:
    return sha256_text(text)[:12]
