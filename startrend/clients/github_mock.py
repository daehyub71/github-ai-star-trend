"""MockGitHub — 기본 테스트 게이트용 (네트워크 0). 픽스처는 실제 API 와 같은 JSON 형식이다.

실제 API 의 제약도 흉내 낸다: Search 1,000건 상한, 히스토리 페이지당 30주·최신 주 먼저.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from startrend.clients.github import (
    HISTORY_PER_PAGE_MAX,
    SEARCH_RESULT_CAP,
    CallStats,
    GitHubError,
    NotFound,
)
from startrend.clients.github_parse import parse_history, parse_repo, parse_search_page
from startrend.core import io
from startrend.core.models import HistoryWeek, RateLimit, Repo, SearchPage


class MockGitHub:
    def __init__(self) -> None:
        self._repos: dict[str, dict[str, Any]] = {}
        self._histories: dict[str, list[dict[str, Any]]] = {}
        self._readmes: dict[str, str] = {}
        self._searches: dict[str, list[str]] = {}
        self.stats = CallStats()
        self.last_rate_limit: RateLimit | None = None

    @classmethod
    def from_fixture_dir(cls, path: Path) -> "MockGitHub":
        """repos.json · search.json · history/<owner>__<repo>.json · readme/<owner>__<repo>.md"""
        gh = cls()
        for raw in io.read_json(path / "repos.json"):
            gh.add_repo(raw)
        if (path / "search.json").exists():
            for query, names in io.read_json(path / "search.json").items():
                gh.add_search(query, names)
        for f in sorted((path / "history").glob("*.json")):
            gh.add_history(_name_from_file(f), io.read_json(f))
        for f in sorted((path / "readme").glob("*.md")):
            gh.add_readme(_name_from_file(f), io.read_text(f))
        return gh

    def add_repo(self, raw: dict[str, Any]) -> None:
        self._repos[raw["full_name"]] = raw

    def add_history(self, full_name: str, weeks_newest_first: list[dict[str, Any]]) -> None:
        self._histories[full_name] = weeks_newest_first

    def add_readme(self, full_name: str, text: str) -> None:
        self._readmes[full_name] = text

    def add_search(self, query: str, full_names: list[str]) -> None:
        self._searches[query] = full_names

    # --- GitHubClient ---

    def get_repo(self, full_name: str) -> Repo:
        self.stats.record("repo", 0.0)
        return parse_repo(self._raw_repo(full_name))

    def search_repositories(
        self, query: str, *, page: int = 1, per_page: int = 100, sort: str = "stars", order: str = "desc"
    ) -> SearchPage:
        self.stats.record("search", 0.0)
        if page * per_page > SEARCH_RESULT_CAP:
            raise GitHubError("Only the first 1000 search results are available", status=422)
        names = self._searches[query] if query in self._searches else self._evaluate(query)
        chunk = names[(page - 1) * per_page: page * per_page]
        raw = {
            "total_count": len(names),
            "incomplete_results": False,
            "items": [self._raw_repo(n) for n in chunk],
        }
        return parse_search_page(raw)

    def star_history(self, full_name: str, *, page: int = 1, per_page: int = HISTORY_PER_PAGE_MAX
                     ) -> list[HistoryWeek]:
        self.stats.record("history", 0.0)
        if per_page > HISTORY_PER_PAGE_MAX:
            raise GitHubError("per_page 는 30 이하", status=422)
        self._raw_repo(full_name)
        weeks = self._histories.get(full_name, [])
        return parse_history(weeks[(page - 1) * per_page: page * per_page])

    def star_count(self, full_name: str) -> int:
        self.stats.record("count", 0.0)
        return int(self._raw_repo(full_name)["stargazers_count"])

    def readme(self, full_name: str) -> str | None:
        # 실제 API 와 같다: README 가 없든 저장소가 없든 404 → None
        self.stats.record("readme", 0.0)
        return self._readmes.get(full_name)

    def _evaluate(self, query: str) -> list[str]:
        """등록되지 않은 질의는 실제 Search 처럼 `stars:` · `created:` 조건으로 계산한다.

        그 밖의 조건이 섞이면 빈 결과를 돌려준다.
        """
        preds: list[Callable[[dict[str, Any]], bool]] = []
        for token in query.split():
            key, _, val = token.partition(":")
            if key == "stars":
                preds.append(_compare(val, lambda raw: int(raw["stargazers_count"]), int))
            elif key == "created":
                preds.append(_compare(val, lambda raw: str(raw["created_at"])[:10], str))
            else:
                return []
        if not preds:
            return []
        hits = [raw for raw in self._repos.values() if all(p(raw) for p in preds)]
        hits.sort(key=lambda raw: (-int(raw["stargazers_count"]), int(raw["id"])))
        return [raw["full_name"] for raw in hits]

    def _raw_repo(self, full_name: str) -> dict[str, Any]:
        try:
            return self._repos[full_name]
        except KeyError:
            raise NotFound(f"{full_name} 없음", status=404) from None


def _compare(expr: str, get: Callable[[dict[str, Any]], Any], conv: Callable[[str], Any]
             ) -> Callable[[dict[str, Any]], bool]:
    """GitHub 검색 비교식: `a..b` · `>=n` · `>n` · `<=n` · `<n` · `n`."""
    if ".." in expr:
        lo, hi = (conv(x) for x in expr.split("..", 1))
        return lambda raw: bool(lo <= get(raw) <= hi)
    op = next((o for o in (">=", "<=", ">", "<") if expr.startswith(o)), "==")
    v = conv(expr[len(op):] if op != "==" else expr)
    tests: dict[str, Callable[[Any], bool]] = {
        ">=": lambda x: bool(x >= v), "<=": lambda x: bool(x <= v),
        ">": lambda x: bool(x > v), "<": lambda x: bool(x < v), "==": lambda x: bool(x == v),
    }
    check = tests[op]
    return lambda raw: check(get(raw))


def _name_from_file(f: Path) -> str:
    owner, _, name = f.stem.partition("__")
    return f"{owner}/{name}"
