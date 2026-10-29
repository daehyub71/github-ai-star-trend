"""저장소 대표 이미지 (결정 60) — 저장소 주인이 올린 소셜 미리보기만 쓴다.

- GitHub GraphQL 한 번(`openGraphImageUrl` · `usesCustomOpenGraphImage`)으로 여러 저장소를 묻는다. 비용 0.
  주인이 올리지 않아 GitHub 이 자동으로 만든 카드는 '없음'으로 본다 — 그 자리는 생성 프롬프트가 맡는다.
- 저장소 README 의 그림은 쓰지 않는다(NFR-9).
- 네트워크는 transport 로만. 토큰은 헤더에만 싣고 예외 메시지에 남기지 않는다(NFR-8).
"""

import json
from collections.abc import Iterable

from startrend.clients.transport import Poster, Transport, UrllibPoster, UrllibTransport

GRAPHQL = "https://api.github.com/graphql"
USER_AGENT = "startrend/0.0.1"
MAX_IMAGE = 5 * 1024 * 1024          # Notion 무료 워크스페이스 파일 한도와 같게 (부록 C-3)
IMAGE_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}


class RepoImageError(Exception):
    pass


def social_previews(full_names: Iterable[str], token: str, *, poster: Poster | None = None,
                    timeout: float = 30.0) -> dict[str, str]:
    """저장소 → 주인이 올린 소셜 미리보기 URL. 올리지 않았거나 없는 저장소는 빠진다."""
    names = list(dict.fromkeys(full_names))
    if not names:
        return {}
    defs: list[str] = []
    fields: list[str] = []
    variables: dict[str, str] = {}
    for i, name in enumerate(names):
        owner, _, repo = name.partition("/")
        defs += [f"$o{i}: String!", f"$n{i}: String!"]
        fields.append(f"r{i}: repository(owner: $o{i}, name: $n{i}) "
                      "{ openGraphImageUrl usesCustomOpenGraphImage }")
        variables[f"o{i}"], variables[f"n{i}"] = owner, repo
    query = f"query({', '.join(defs)}) {{ {' '.join(fields)} }}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json",
               "User-Agent": USER_AGENT}
    resp = (poster or UrllibPoster())(GRAPHQL, headers,
                                      json.dumps({"query": query, "variables": variables}).encode(), timeout)
    if resp.status != 200:
        raise RepoImageError(f"GitHub GraphQL: HTTP {resp.status}")
    try:
        data = json.loads(resp.body).get("data") or {}
    except (ValueError, AttributeError) as e:
        raise RepoImageError(f"GitHub GraphQL: 응답을 읽지 못했다 ({e})") from e
    out: dict[str, str] = {}
    for i, name in enumerate(names):
        r = data.get(f"r{i}") or {}
        url = r.get("openGraphImageUrl")
        if r.get("usesCustomOpenGraphImage") is True and isinstance(url, str) and url.startswith("https://"):
            out[name] = url
    return out


def download(url: str, *, transport: Transport | None = None, timeout: float = 30.0) -> tuple[bytes, str]:
    """그림 바이트와 확장자. 그림이 아니거나 5 MiB 를 넘으면 RepoImageError."""
    resp = (transport or UrllibTransport())("GET", url, {"User-Agent": USER_AGENT}, timeout)
    if resp.status != 200:
        raise RepoImageError(f"그림 받기: HTTP {resp.status}")
    ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
    if ctype not in IMAGE_TYPES:
        raise RepoImageError(f"그림이 아니다: {ctype or '형식 없음'}")
    if len(resp.body) > MAX_IMAGE:
        raise RepoImageError(f"그림이 너무 크다: {len(resp.body):,} 바이트")
    return resp.body, IMAGE_TYPES[ctype]
