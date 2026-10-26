"""clients.trending — GitHub Trending 페이지 파서 (probe 대조용, SPEC R11: 운영 의존으로 쓰지 않는다)."""

from startrend.clients import trending
from tests import synth

HTML = (synth.FIXTURES / "trending" / "weekly.html").read_text(encoding="utf-8")


def test_trending_parse_rows():
    rows = trending.parse_trending(HTML)
    assert [r.full_name for r in rows] == ["synth-lab/agent-kit", "synth-lab/mcp-files"]


def test_trending_parse_numbers_with_commas():
    r = trending.parse_trending(HTML)[0]
    assert r.stars_total == 48210
    assert r.stars_period == 15072


def test_trending_parse_empty_page():
    assert trending.parse_trending("<html></html>") == []


def test_trending_row_without_period_stars_is_skipped():
    html = '<article class="Box-row"><h2 class="h3"><a href="/a/b">b</a></h2></article>'
    assert trending.parse_trending(html) == []


def test_trending_url():
    assert trending.trending_url("weekly") == "https://github.com/trending?since=weekly"
