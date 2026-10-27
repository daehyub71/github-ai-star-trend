"""core.taxonomy — 분류 체계 v1 (FR-3.2·3.3·3.4, 결정 20 · 부록 A)."""

from pathlib import Path

import pytest

from startrend.core import taxonomy as tx

ROOT = Path(__file__).resolve().parents[1]
APPENDIX_A = [
    "에이전트 프레임워크", "코딩 에이전트·IDE", "MCP 서버·도구", "에이전트 스킬·프롬프트", "추론·서빙",
    "로컬 LLM 실행", "모델·가중치", "학습·파인튜닝", "RAG·검색", "벡터DB·메모리", "평가·관측(LLMOps)",
    "멀티모달(이미지·음성·영상)", "브라우저·컴퓨터 사용 자동화", "문서·데이터 파싱", "기타 AI",
]


def test_taxonomy_v1_matches_spec_appendix_a():
    t = tx.load(ROOT / "data" / "taxonomy.toml")
    assert t.version == 1
    assert [c.name for c in t.categories] == APPENDIX_A
    assert t.types == ("도구/라이브러리", "큐레이션 목록", "교육자료", "모델/데이터", "기타")
    assert all(c.id.isascii() and c.desc for c in t.categories)


def test_taxonomy_resolve_by_name_or_id():
    t = tx.load(ROOT / "data" / "taxonomy.toml")
    mcp = t.resolve("MCP 서버·도구")
    assert mcp is not None and t.resolve(mcp) == mcp
    assert t.resolve("  MCP 서버·도구 ") == mcp  # 앞뒤 공백은 무시
    assert t.resolve("없는 카테고리") is None
    assert t.resolve(None) is None


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "t.toml"
    p.write_text(body, encoding="utf-8")
    return p


GOOD = """
version = 2
types = ["도구/라이브러리", "기타"]
[[category]]
id = "a"
name = "가"
desc = "설명"
[[category]]
id = "b"
name = "나"
desc = "설명"
[mapping]
"v1:old" = "a"
"""


def test_taxonomy_mapping_follows_renamed_categories(tmp_path):
    t = tx.load(_write(tmp_path, GOOD))
    assert t.map_old("v1:old") == "a"   # 이전 버전 id → 지금 id (추이 그래프가 이어지게)
    assert t.map_old("v1:gone") is None


@pytest.mark.parametrize("bad, why", [
    (GOOD.replace('id = "b"', 'id = "a"'), "id"),
    (GOOD.replace('name = "나"', 'name = "가"'), "이름"),
    (GOOD.replace('"v1:old" = "a"', '"v1:old" = "zzz"'), "매핑"),
    (GOOD.replace('types = ["도구/라이브러리", "기타"]', "types = []"), "유형"),
    (GOOD.replace("version = 2", ""), "version"),
])
def test_taxonomy_rejects_inconsistent_files(tmp_path, bad, why):
    with pytest.raises(tx.TaxonomyError, match=why):
        tx.load(_write(tmp_path, bad))
