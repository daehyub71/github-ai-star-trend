"""blog 단계 (SPEC FR-16, 결정 36·37·39·59·60) — MockLLM 으로 비용 0.

글 구성(결정 60): 지금 뜨는 저장소의 흐름 개괄 → TOP 10 저장소마다 1. 무엇인가 · 2. 왜 지금 떴나 ·
3. 활용 사례(저장소 하나에 한글 500자 안팎) → 주의할 점 · 한 장 요약.
대표 이미지는 저장소 소셜 미리보기, 없으면 생성 프롬프트.
고정 틀(제목·정보 블록·숫자·링크·글 모음·해시태그)은 코드가 채운다.
형식 검사기가 막는 것: 글 안의 URL·마크다운 기호, 목록 밖 출처, 출처 없는 주장, 입력에 없는 숫자,
합쇼체가 아닌 문장, 순서가 틀린 TOP 목록, 분량.
"""

import copy
import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from startrend.budget import BudgetMeter
from startrend.clients.llm import LLMResponse, MockLLM, Usage
from startrend.stages import blog

W = "2026-10-18"

CARD = """---
repo: {name}
repo_id: {i}
week: 2026-10-18
as_of: 2026-10-24
---
# {name}

## ① 3줄 요약
- **무엇인지** — {name} 는 에이전트 도구다.
- **왜 지금 떴나** — 2026-10-20 릴리스 뒤 스타가 몰렸다.
- **어떤 의미인지** — 로컬에서 돌린다.

## ③ 왜 지금 떴나
- 2026-10-20 v1.2 릴리스. [GitHub 릴리스](https://github.com/{name}/releases/tag/v1.2) (확인)
- HN 에서 비교 기준으로 언급됐다. [HN 댓글](https://news.ycombinator.com/item?id={i}00) · \
[{name}](https://github.com/{name}) (확인)

## ④ 무엇인가
에이전트를 로컬에서 돌린다. [README](https://github.com/{name}#readme)

## ⑥ 활용사례
- 작업을 나눠 맡긴다. [HN 댓글](https://news.ycombinator.com/item?id={i}00) (확인)

## ⑦ 한계·리스크
- 이 섹션은 블로그 입력에 넣지 않는다. 비밀문구XYZ

## 근거
- E1 [v1.2 릴리스](https://github.com/{name}/releases/tag/v1.2) — GitHub 릴리스 · 2026-10-20
- E2 [HN 댓글](https://news.ycombinator.com/item?id={i}00) — HN · 2026-10-21
- E3 [README](https://github.com/{name}#readme) — GitHub README
"""


def _e(i: int, name: str, cat: str = "rag", **over: Any) -> dict[str, Any]:
    e = {"id": i, "full_name": name, "category": cat, "type": "도구/라이브러리", "stars_end": 300_000 + i,
         "gain": 69_361 - i, "growth": 0.2234, "start_stars": 8_000, "created": "2026-10-01", "rank": i,
         "description": f"{name} desc", "is_ai": True}
    e.update(over)
    return e


def _src(tmp: Path) -> tuple[Path, Path]:
    site, priv = tmp / "site", tmp / "priv"
    (site / "weeks").mkdir(parents=True)
    (priv / "cards").mkdir(parents=True)
    (priv / "briefings").mkdir()
    (site / "index.json").write_text(json.dumps({
        "weeks": [W], "latest": W, "types": ["도구/라이브러리"],
        "categories": [{"id": "rag", "name": "RAG·검색"}, {"id": "mcp-tools", "name": "MCP 서버·도구"}]},
        ensure_ascii=False), encoding="utf-8")
    week = {"week": W, "week_end": "2026-10-24", "axes": {
        "gain": {"all": [], "ai": [_e(1, "o/a", "mcp-tools"), _e(2, "o/b"), _e(3, "o/c"), _e(5, "o/nocard")]},
        "fresh": {"all": [], "ai": [_e(3, "o/c")]},
        "growth": {"all": [], "ai": [_e(2, "o/b")]},
        "total": {"all": [], "ai": [_e(1, "o/a", "mcp-tools")]}}}
    (site / "weeks" / f"{W}.json").write_text(json.dumps(week, ensure_ascii=False), encoding="utf-8")
    refs = []
    for i, name in ((1, "o/a"), (2, "o/b"), (3, "o/c")):
        slug = name.replace("/", "__")
        (priv / "cards" / f"{slug}.md").write_bytes(CARD.format(name=name, i=i).encode("utf-8"))
        refs.append({"repo_id": i, "full_name": name, "as_of": "2026-10-24", "slug": slug})
    (priv / "cards" / "index.json").write_text(json.dumps(refs), encoding="utf-8")
    (priv / "briefings" / f"{W}.md").write_bytes(
        f"---\nweek: {W}\n---\n# 이번 주 AI 트렌드\n\n로컬 에이전트가 앞섰다.\n".encode())
    return site, priv


@pytest.fixture
def bi(tmp_path: Path) -> blog.BlogInput:
    site, priv = _src(tmp_path)
    return blog.load_input(site, priv, W)


def _part(sentence: str, n: int, sources: list[str]) -> dict[str, Any]:
    return {"text": " ".join([sentence] * n), "sources": sources}


SCENE = ("A two-step explainer laid out left to right. On the left, a small friendly robot sits at a desk "
         "sorting a messy pile of task cards that spill over the edges. On the right, the same cards are "
         "neatly stacked into three trays of different colors, and the robot leans back looking relaxed. "
         "A thin curved "
         "arrow connects the two halves. Place an empty rounded label tag under each half and one above the "
         "trays, keeping plenty of white space around every element so short labels can be added later.")
IDEA = {"teaches": "작업을 나눠 맡기는 흐름", "scene": SCENE,
        "labels": ["어지러운 작업", "나눠 맡기기", "정리된 결과"]}
COVER = {"teaches": "이번 주 별이 몰린 곳", "scene": SCENE, "labels": ["에이전트", "도구", "별"]}


def _repo(ref: str, name: str) -> dict[str, Any]:
    return {"ref": ref, "subtitle": "릴리스 뒤에 몰린 관심",
            "what": _part(f"{name} 는 에이전트를 로컬에서 돌리는 도구입니다.", 5, [ref]),
            "why_now": _part("10월 20일 릴리스 뒤에 별이 몰렸습니다.", 6, [f"{ref}:E1"]),
            "use_cases": _part("개발자는 이 도구로 작업을 나눠 맡깁니다.", 6, [f"{ref}:E2"]),
            "image": IDEA}


GOOD: dict[str, Any] = {
    "title_points": ["MCP 도구가 1위", "새 저장소 셋", "로컬 에이전트"],
    "intro": "이번 주 GitHub 에서 가장 많은 별을 받은 AI 저장소는 무엇일까요? 숫자와 근거로 따라가 봅니다.",
    "overview": {"heading": "로컬 에이전트가 앞선 한 주", "paras": [
        {"text": "이번 주에는 에이전트를 로컬에서 돌리는 도구가 앞섰습니다.", "sources": ["R1"]},
        {"text": "검색 도구도 함께 올라왔습니다.", "sources": ["R2", "R3"]}]},
    "repos": [_repo("R1", "o/a"), _repo("R2", "o/b"), _repo("R3", "o/c")],
    "cover": COVER,
    "misreadings": [{"claim": "별이 많으면 좋은 도구일까요?",
                     "answer": "관심의 크기일 뿐, 품질은 직접 확인합니다."}] * 3,
    "summary": "이번 주는 로컬 에이전트 도구가 앞섰습니다.",
    "next": "다음 글에서는 다음 주 흐름을 다룹니다.",
    "tags": ["MCP", "로컬 LLM", "에이전트"],
}


def _draft(d: dict[str, Any] | None = None) -> blog.BlogDraft:
    return blog.parse_blog(json.dumps(d or GOOD, ensure_ascii=False))


def _with(path: str, value: Any) -> dict[str, Any]:
    """'repos.0.what.text' 같은 경로의 값을 바꾼 GOOD 사본."""
    d = copy.deepcopy(GOOD)
    cur: Any = d
    keys = path.split(".")
    for k in keys[:-1]:
        cur = cur[int(k)] if isinstance(cur, list) else cur[k]
    last = keys[-1]
    if isinstance(cur, list):
        cur[int(last)] = value
    else:
        cur[last] = value
    return d


def test_blog_episode_counts_weeks_from_the_series_start():
    assert blog.episode("2026-10-18") == 1 and blog.episode("2026-11-01") == 3


def test_blog_input_takes_the_top_rising_repos_with_cards(bi):
    assert [r.full_name for r in bi.repos] == ["o/a", "o/b", "o/c"]      # 카드 없는 o/nocard 는 빠진다
    assert [r.ref for r in bi.repos] == ["R1", "R2", "R3"] and bi.repos[0].rank == 1
    a = bi.repos[0]
    assert "GitHub 릴리스 [R1:E1]" in a.card and "HN 댓글 [R1:E2]" in a.card and "o/a [R1]" in a.card
    assert "README [R1:E3]" in a.card and "④ 무엇인가" in a.card and "⑥ 활용사례" in a.card
    assert "https://" not in a.card and "비밀문구XYZ" not in a.card       # ⑦ 등 다른 섹션은 넣지 않는다
    assert bi.sources["R1:E1"] == ("v1.2 릴리스", "https://github.com/o/a/releases/tag/v1.2")
    assert bi.sources["R3"] == ("o/c", "https://github.com/o/c")


def test_blog_user_message_keeps_urls_out_and_marks_data(bi):
    msg = blog.user_message(bi)
    assert "http" not in msg and "<document>" in msg and "<evidence>" in msg
    assert "지금 뜨는 저장소 1위 o/a" in msg and "+69,360" in msg


def test_blog_accepts_a_good_draft(bi):
    assert blog.check_draft(_draft(), bi) == []


@pytest.mark.parametrize("path, value, word", [
    ("repos.0.what.text", "자세한 건 https://x.example 를 봅니다. " * 12, "URL"),
    ("repos.0.what.text", "**굵게** 씁니다. " * 15, "마크다운"),
    ("repos.0.why_now.sources", ["R9"], "R9"),
    ("repos.0.use_cases.sources", [], "출처"),
    ("overview.paras.0.text", "별 12,345개를 받았습니다.", "12345"),
    ("overview.paras.0.text", "이것은 도구다. 좋다. 빠르다. 크다. 작다.", "합쇼체"),
    ("repos.1.ref", "R3", "순서"),
    ("repos.2.what.text", "짧습니다.", "분량"),
    ("repos.0.image.scene", "A robot at a desk, no text.", "프롬프트"),
    ("repos.0.image.labels", [], "라벨"),
    ("cover.labels", ["아주 아주 긴 라벨 이름입니다"], "라벨"),
])
def test_blog_check_rejects(bi, path, value, word):
    errors = blog.check_draft(_draft(_with(path, value)), bi)
    assert errors and any(word in e for e in errors), errors


def test_blog_parse_rejects_wrong_shape():
    with pytest.raises(ValueError):
        blog.parse_blog(json.dumps({**GOOD, "title_points": ["하나", "둘"]}, ensure_ascii=False))
    with pytest.raises(ValueError):
        blog.parse_blog("not json")


IMG = "https://repository-images.githubusercontent.com/1/abc"


def test_blog_render_follows_the_agreed_layout(bi):
    title, body, res = blog.render(bi, _draft(), published=(), images={"o/a": IMG})
    assert title == "🤖 깃허브 AI 트렌드 주간 동향 1회 🤖 MCP 도구가 1위 · 새 저장소 셋 · 로컬 에이전트"
    assert "「깃허브 AI 트렌드 주간 동향」의 1번째 글입니다." in body
    assert "***깃허브 AI 트렌드 주간 동향 1회 정보***" in body
    assert "⭐ 집계 기간 : 2026년 10월 18일(일) ~ 10월 24일(토), UTC 기준" in body
    order = ["### 이번 주 흐름 — 로컬 에이전트가 앞선 한 주", "### TOP 3 — 지금 뜨는 AI 저장소",
             "### 1위 o/a — 릴리스 뒤에 몰린 관심", "### 3위 o/c", "### 이번 주 숫자를 읽을 때 주의할 점",
             "### 한 장 요약"]
    at = [body.index(h) for h in order]
    assert at == sorted(at)
    assert "1위 [o/a](https://github.com/o/a) — 지난 주 +69,360 스타 · 누적 300,001 · MCP 서버·도구" in body
    assert "\n1. 무엇인가 — o/a 는" in body and "\n2. 왜 지금 떴나 — 10월 20일" in body
    assert "\n3. 활용 사례 — 개발자는" in body
    assert "[v1.2 릴리스](https://github.com/o/a/releases/tag/v1.2)" in body
    assert f"![o/a 대표 이미지]({IMG})" in body and "이미지: o/a 저장소의 소셜 미리보기" in body
    o_b = body[body.index("### 2위 o/b"):body.index("### 3위 o/c")]
    assert ("> 🎨 그림 자리 — 작업을 나눠 맡기는 흐름 · 얹을 라벨: 어지러운 작업 · 나눠 맡기기 · "
            "정리된 결과") in o_b
    assert "```text\nA two-step explainer" in o_b and blog.STYLE in o_b and "![" not in o_b
    assert "> 🎨 대표 이미지 자리 — 이번 주 별이 몰린 곳 · 얹을 라벨: 에이전트 · 도구 · 별" in body
    tags = body.rstrip().splitlines()[-1]
    assert tags.startswith("#깃허브AI트렌드") and "#로컬LLM" in tags and tags.endswith("#50VibeLog")
    assert "vercel.app" not in body                     # FR-16.5 — 사이트 주소는 넣지 않는다
    assert res.excluded == ()


def test_blog_collection_lists_published_posts(tmp_path):
    site, priv = _src(tmp_path)
    data = json.loads((site / "weeks" / f"{W}.json").read_text(encoding="utf-8"))
    data["week"], data["week_end"] = "2026-10-25", "2026-10-31"
    (site / "weeks" / "2026-10-25.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    bi2 = blog.load_input(site, priv, "2026-10-25")
    _, body, res = blog.render(bi2, _draft(), published=((1, "첫 글", "https://blog.naver.com/dayhyub/1"),),
                               images={})
    assert "▶ 1회 첫 글 : [https://blog.naver.com/dayhyub/1](https://blog.naver.com/dayhyub/1)" in body
    assert "▶ 2회 MCP 도구가 1위 · 새 저장소 셋 · 로컬 에이전트 (이 글)" in body
    assert res.excluded == ()


def test_blog_images_doc_places_found_images_and_prompts(bi):
    doc = blog.images_doc(bi, _draft(), images={"o/a": IMG}, files={"o/a": "img/o__a.png"})
    assert "| 1위 o/a — 릴리스 뒤에 몰린 관심 | img/o__a.png (저장소 소셜 미리보기) |" in doc
    assert "| 2위 o/b — 릴리스 뒤에 몰린 관심 | 생성 프롬프트 2 |" in doc
    assert "### 0. 대표 이미지(글 맨 위)" in doc and "### 2. o/b" in doc and "(대안)" in doc
    assert "- 가르칠 것: 작업을 나눠 맡기는 흐름" in doc
    assert "- 얹을 라벨: 어지러운 작업 · 나눠 맡기기 · 정리된 결과" in doc
    assert doc.count(SCENE) == 4 and blog.STYLE in doc


def _resp(obj: Any) -> LLMResponse:
    text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    return LLMResponse(text=text, stop_reason="end_turn", usage=Usage(10_000, 6_000), model="claude-opus-5-5")


def test_blog_run_writes_post_and_retries_once(bi, tmp_path):
    bad = _with("overview.paras.0.text", "이것은 도구다. 좋다. 빠르다. 크다. 작다.")
    llm = MockLLM([_resp(bad), _resp(GOOD)])
    stats = blog.run_blog(blog.BlogWriter(llm), bi, work_dir=tmp_path / "w", today=date(2026, 10, 29),
                          published=(), images={}, files={}, log=lambda m: None)
    assert stats["written"] is True and len(llm.requests) == 2
    assert "합쇼체" in llm.requests[1].user
    out = tmp_path / "w" / W / "blog"
    post = (out / "post.md").read_text(encoding="utf-8")
    assert post.startswith("# 🤖 깃허브 AI 트렌드 주간 동향 1회 🤖")
    assert json.loads((out / "draft.json").read_text(encoding="utf-8"))["title_points"][0] == "MCP 도구가 1위"
    assert json.loads((out / "gate.json").read_text(encoding="utf-8"))["excluded"] == []
    assert "생성 프롬프트" in (out / "images.md").read_text(encoding="utf-8")


def test_blog_run_gives_up_after_two_bad_answers(bi, tmp_path):
    llm = MockLLM([_resp("not json"), _resp("still not json")])
    stats = blog.run_blog(blog.BlogWriter(llm), bi, work_dir=tmp_path / "w", today=date(2026, 10, 29),
                          published=(), images={}, files={}, log=lambda m: None)
    assert stats["written"] is False and stats["error"]
    assert not (tmp_path / "w" / W / "blog" / "post.md").exists()


def test_blog_run_stops_at_the_budget(bi, tmp_path):
    meter = BudgetMeter(MockLLM([]), cap_usd=0.0001)
    stats = blog.run_blog(blog.BlogWriter(meter), bi, work_dir=tmp_path / "w", today=date(2026, 10, 29),
                          published=(), images={}, files={}, log=lambda m: None)
    assert stats["stopped"] == "budget" and not (tmp_path / "w" / W / "blog").exists()


def test_blog_dry_run_makes_no_calls(bi):
    llm = MockLLM([])
    est = blog.dry_run(blog.BlogWriter(llm), bi)
    assert llm.requests == [] and est["llm_calls"] == 1 and est["top"] == ["o/a", "o/b", "o/c"]
    lo, hi = est["total_usd"]
    assert 0 < lo < hi


def test_blog_rerender_from_the_saved_draft_costs_nothing(bi, tmp_path):
    # 프롬프트·틀만 고쳤을 때 LLM 을 다시 부르지 않고 저장된 초안으로 다시 그린다
    w = tmp_path / "w"
    blog.run_blog(blog.BlogWriter(MockLLM([_resp(GOOD)])), bi, work_dir=w, today=date(2026, 10, 29),
                  published=(), images={"o/a": IMG}, files={"o/a": "img/o__a.png"}, log=lambda m: None)
    out = w / W / "blog"
    before = (out / "post.md").read_text(encoding="utf-8")
    assert blog.load_draft(out / "draft.json") == _draft()
    (out / "post.md").unlink()
    stats = blog.rerender(bi, work_dir=w, published=(), log=lambda m: None)
    assert stats["written"] is True and (out / "post.md").read_text(encoding="utf-8") == before
    assert "img/o__a.png" in (out / "images.md").read_text(encoding="utf-8")
    # 예전 meta.json 에는 받은 파일 경로가 없었다 — img/ 폴더에서 찾는다
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    del meta["files"]
    (out / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (out / "img").mkdir()
    (out / "img" / "o__a.jpg").write_bytes(b"x")
    blog.rerender(bi, work_dir=w, published=(), log=lambda m: None)
    assert "img/o__a.jpg (저장소 소셜 미리보기)" in (out / "images.md").read_text(encoding="utf-8")


def test_blog_rerender_needs_a_saved_draft(bi, tmp_path):
    stats = blog.rerender(bi, work_dir=tmp_path / "w", published=(), log=lambda m: None)
    assert stats["written"] is False and "draft.json" in stats["error"]
