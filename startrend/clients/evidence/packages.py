"""패키지 근거 (SPEC FR-5.4, 결정 44, 부록 C-2) — 저장소 → PyPI·npm 패키지 → 주간 다운로드·"패키지 의존 수".

- 저장소 → 패키지: 저장소 URL 로 ecosyste.ms 를 조회하면 이름만 비슷한 포크 패키지가 섞이고 응답이 수십 MB 다
  (2026-10-28 실측: openai-python 11.6MB·PyPI 10개 중 진짜 1개, vercel/ai 81MB). 그래서 저장소 이름에서 패키지
  이름 후보를 만들어 **이름으로** 조회하고, 그 패키지의 저장소 URL 이 우리 저장소일 때만 쓴다
  (이름 일치로 거르기).
- 다운로드: PyPI 는 pypistats `recent`(last_week), npm 은 다운로드 API `point/last-week`. npm 은 늦게 반영되고
  0 이 섞인다 — 0 은 그대로 믿지 않고 모름(None)으로 둔다.
- 의존 수는 GitHub "Used by" 와 다른 수치다 — "패키지 의존 수"로 부르고
  출처(ecosyste.ms, CC BY-SA 4.0)를 적는다.
- 숫자는 카드에 코드가 넣는다(FR-6.5). 근거 URL 은 레지스트리의 패키지 페이지다.
"""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlencode

from startrend.clients.evidence.base import SourceError, Target
from startrend.clients.transport import Transport, TransportError
from startrend.core import evidence as ev

LOOKUP = "https://packages.ecosyste.ms/api/v1/packages/lookup"
USER_AGENT = "startrend/0.0.1 (+https://github.com/daehyub71/github-ai-star-trend)"
ATTRIBUTION = "ecosyste.ms (CC BY-SA 4.0)"
ECOSYSTEMS = ("pypi", "npm")
_LABEL = {"pypi": "PyPI", "npm": "npm"}
_SUFFIXES = ("-python", "-py", ".py", "-js", ".js", "-node", "-ts", "-sdk", "-cli")
_PREFIXES = ("python-", "py-", "node-", "js-")


def candidates(full_name: str, ecosystem: str) -> list[str]:
    """패키지 이름 후보 — 저장소 이름, 언어 접두·접미어를 뗀 이름, npm 은 @owner/repo 도."""
    owner, repo = full_name.lower().split("/", 1)
    names = [repo]
    names += [repo[: -len(s)] for s in _SUFFIXES if repo.endswith(s)]
    names += [repo[len(p):] for p in _PREFIXES if repo.startswith(p)]
    if ecosystem == "npm":
        names.append(f"@{owner}/{repo}")
    out: list[str] = []
    for n in names:
        if n and n not in out:
            out.append(n)
    return out


class PackagesSource:
    def __init__(self, transport: Transport, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC),
                 timeout: float = 60.0):
        self._t = transport
        self._clock = clock
        self.timeout = timeout
        self.calls = 0

    @property
    def name(self) -> str:
        return "package"

    def _get(self, url: str) -> tuple[int, Any]:
        self.calls += 1
        resp = self._t("GET", url, {"User-Agent": USER_AGENT, "Accept": "application/json"}, self.timeout)
        if resp.status != 200:
            return resp.status, None
        return 200, json.loads(resp.body)

    def _lookup(self, ecosystem: str, name: str) -> list[dict[str, Any]]:
        url = f"{LOOKUP}?{urlencode({'ecosystem': ecosystem, 'name': name})}"
        try:
            status, body = self._get(url)
        except TransportError as e:
            raise SourceError(f"ecosyste.ms 연결 실패: {e}") from e
        except ValueError as e:
            raise SourceError(f"ecosyste.ms 응답이 JSON 이 아니다 ({ecosystem} {name})") from e
        if status == 404:
            return []
        if status != 200 or not isinstance(body, list):
            raise SourceError(f"ecosyste.ms {status} ({ecosystem} {name})")
        return [p for p in body if isinstance(p, dict)]

    def _weekly(self, ecosystem: str, name: str) -> int | None:
        """지난 주 다운로드. 실패하면 예외 — 부르는 쪽이 partial 로 적는다."""
        if ecosystem == "pypi":
            status, body = self._get(f"https://pypistats.org/api/packages/{quote(name, safe='')}/recent")
            n = body["data"]["last_week"] if status == 200 else None
        else:
            npm = "https://api.npmjs.org/downloads/point/last-week/"
            status, body = self._get(npm + quote(name, safe="@/"))
            n = body["downloads"] if status == 200 else None
        if status != 200:
            raise SourceError(f"{ecosystem} 다운로드 {status}")
        return int(n) if n else None       # 0 은 모름으로 (npm 지연·0 섞임)

    def collect(self, target: Target) -> list[ev.Evidence]:
        now = self._clock()
        want = target.full_name.lower()
        docs: list[ev.Evidence] = []
        for eco in ECOSYSTEMS:
            pkg = None
            for name in candidates(target.full_name, eco):
                pkg = next((p for p in self._lookup(eco, name)
                            if ev.github_repo(str(p.get("repository_url") or "")) == want), None)
                if pkg:
                    break
            if pkg is None:
                continue
            name = str(pkg["name"])
            partial: list[str] = []
            try:
                weekly = self._weekly(eco, name)
            except (SourceError, TransportError, ValueError, KeyError, TypeError):
                weekly = None
                partial.append("downloads")
            fallback = (f"https://pypi.org/project/{name}/" if eco == "pypi"
                        else f"https://www.npmjs.com/package/{name}")
            docs.append(ev.make(
                url=str(pkg.get("registry_url") or fallback), source="package", kind="package",
                title=f"{_LABEL[eco]} {name}", text=str(pkg.get("description") or ""), fetched_at=now,
                extra={"ecosystem": eco, "package": name, "downloads_last_week": weekly,
                       "downloads_week_source": "pypistats.org" if eco == "pypi" else "api.npmjs.org",
                       "downloads_last_month": pkg.get("downloads"),
                       "dependent_repos": pkg.get("dependent_repos_count"),
                       "dependent_packages": pkg.get("dependent_packages_count"),
                       "dependents_label": "패키지 의존 수", "attribution": ATTRIBUTION, "partial": partial}))
        return docs
