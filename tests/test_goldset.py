"""stages.goldset — 분류 정답 세트 후보 뽑기 (FR-14.1, 결정 41). 비용 0, 결정론."""

from collections import Counter
from datetime import UTC, date, datetime

from startrend.budget import BudgetExceeded
from startrend.clients import decision as dc
from startrend.clients.github_mock import MockGitHub
from startrend.core import io
from startrend.core.models import Repo
from startrend.stages import goldset as gs
from tests import synth

T0 = datetime(2023, 1, 1, tzinfo=UTC)


def repo(rid: int, *, desc: str | None = "a tool", topics: tuple[str, ...] = (), stars: int = 2000,
         archived: bool = False, name: str | None = None) -> Repo:
    full = name or f"o{rid}/r{rid}"
    return Repo(rid, full, desc, topics, "Python", stars, 10, 1, T0, None, archived, False)


# --- AI 신호 (정답이 아니라 고루 뽑기 위한 대리 지표) ---


def test_goldset_signal_strong_from_topic_or_specific_word():
    assert gs.signal(repo(1, topics=("llm",))) == "strong"
    assert gs.signal(repo(2, desc="Fast inference server for LLMs")) == "strong"
    mcp = repo(3, desc="Model Context Protocol server for Notion", name="x/notion-mcp")
    assert gs.signal(mcp) == "strong"


def test_goldset_signal_weak_from_generic_ai_words():
    assert gs.signal(repo(1, desc="An AI-powered photo editor")) == "weak"
    assert gs.signal(repo(2, desc="Smart chat bot for Discord")) == "weak"


def test_goldset_signal_none():
    assert gs.signal(repo(1, desc="A static site generator")) == "none"
    assert gs.signal(repo(2, desc=None)) == "none"
    assert gs.signal(repo(3, desc="Email client", name="o/maillist")) == "none"  # 'ai' 가 단어 안에 있을 뿐


def test_goldset_band():
    assert [gs.band(s) for s in (500, 1000, 4999, 5000, 49_999, 50_000)] == \
        ["<1k", "1k-5k", "1k-5k", "5k-50k", "5k-50k", "50k+"]


# --- 뽑기 ---


def _population(n: int = 900) -> dict[int, Repo]:
    pop: dict[int, Repo] = {}
    for i in range(1, n + 1):
        kind = i % 3
        desc = ("LLM agent framework", "An AI-powered editor", "A web server")[kind]
        stars = (1500, 8000, 70_000, 600)[i % 4]
        pop[i] = repo(i, desc=desc, stars=stars)
    return pop


def test_goldset_sample_quotas():
    pop = _population()
    ranked = set(range(1, 101))
    picks = gs.sample(pop, ranked=ranked, new=set(range(800, 901)), seed=1)
    assert len(picks) == 200 and len({p["repo_id"] for p in picks}) == 200
    groups = Counter(p["group"] for p in picks)
    assert groups == {"ranked": 60, "strong": 60, "weak": 40, "none": 40}
    assert all(p["repo_id"] in ranked for p in picks if p["group"] == "ranked")


def test_goldset_blind_spread():
    picks = gs.sample(_population(), ranked=set(range(1, 101)), new=set(), seed=1)
    blind = Counter(p["group"] for p in picks if p["blind"])
    assert blind == {"ranked": 10, "strong": 7, "weak": 7, "none": 6}


def test_goldset_spreads_star_bands_within_a_group():
    picks = gs.sample(_population(), ranked=set(), new=set(), seed=1)
    bands = {p["band"] for p in picks if p["group"] == "strong"}
    assert bands == {"<1k", "1k-5k", "5k-50k", "50k+"}


def test_goldset_deterministic_by_seed():
    pop = _population()
    a = [p["repo_id"] for p in gs.sample(pop, ranked=set(), new=set(), seed=7)]
    b = [p["repo_id"] for p in gs.sample(pop, ranked=set(), new=set(), seed=7)]
    c = [p["repo_id"] for p in gs.sample(pop, ranked=set(), new=set(), seed=8)]
    assert a == b and a != c


def test_goldset_fills_short_groups_from_the_rest():
    pop = _population(300)  # 신호별 100개 — 랭킹 진입 저장소는 5개뿐
    picks = gs.sample(pop, ranked={1, 2, 3, 4, 5}, new=set(), seed=1)
    assert len(picks) == 200
    assert sum(p["group"] == "ranked" for p in picks) == 5


def test_goldset_excludes_archived():
    pop = _population(400)
    pop[401] = repo(401, desc="LLM toolkit", archived=True)
    ids = {p["repo_id"] for p in gs.sample(pop, ranked={401}, new=set(), seed=1)}
    assert 401 not in ids


def test_goldset_record_fields():
    p = gs.sample(_population(), ranked=set(), new={3}, seed=1)[0]
    assert set(p) == {"repo_id", "full_name", "description", "topics", "language", "stars", "created",
                      "group", "signal", "band", "new", "blind"}


# --- 초안 (P2-11, 결정 41) — 판정은 mock, 저장소 정보는 MockGitHub ---


def _cands(n: int) -> list[dict[str, object]]:
    return [{"repo_id": i, "full_name": f"o/r{i}", "blind": i <= 2} for i in range(1, n + 1)]


def _gh(ids: list[int]) -> MockGitHub:
    gh = MockGitHub()
    for i in ids:
        gh.add_repo(synth.repo(f"o/r{i}", id=i, stars=1000 + i, description=f"d{i}", topics=["llm"]))
        gh.add_readme(f"o/r{i}", f"# r{i}")
    return gh


def test_goldset_draft_inputs_fetch_repo_and_readme():
    items, missing = gs.draft_inputs(_gh([1, 2]), _cands(3), log=lambda m: None)
    assert [it.repo_id for it in items] == [1, 2] and missing == ["o/r3"]   # 지운 저장소는 빼고 기록
    assert items[0].readme_head == "# r1" and items[0].description == "d1" and items[0].topics == ("llm",)


def test_goldset_run_draft_writes_a_prediction_row_per_candidate(tmp_path):
    ai = dc.Decision(status="ok", is_ai=True, type="도구/라이브러리", category="rag", reason="r", attempts=1)
    decider = dc.MockDecider({1: ai, 2: dc.Decision(status="ok", is_ai=False, type="교육자료"),
                              3: dc.Decision(status="unclassified", error="x")})
    out = tmp_path / "drafts.jsonl"
    stats = gs.run_draft(_gh([1, 2, 3]), decider, _cands(3), out=out, today=date(2026, 10, 27),
                         log=lambda m: None)
    rows = list(io.read_jsonl(out))
    assert [r["repo_id"] for r in rows] == [1, 2, 3] and stats["decided"] == 3 and stats["stopped"] is None
    assert rows[0] == {"repo_id": 1, "full_name": "o/r1", "blind": True, "status": "ok", "is_ai": True,
                       "type": "도구/라이브러리", "category": "rag", "secondary": None, "reason": "r",
                       "attempts": 1, "error": None, "confidence": None, "fingerprint": "mock",
                       "at": "2026-10-27"}
    assert rows[2]["status"] == "unclassified"


def test_goldset_run_draft_writes_nothing_when_the_budget_stops_before_any_decision(tmp_path):
    # 회귀(2026-10-27): 제출 전에 예산으로 막히면 빈 초안 파일이 남았다 — 판정이 없으면 쓰지 않는다
    class Blocked(dc.MockDecider):
        def classify_many(self, items, *, batch=None, on_decision=None):
            raise BudgetExceeded("classify 2건: 최악 $3.04 — 남은 예산 $3.00")

    out = tmp_path / "drafts.jsonl"
    stats = gs.run_draft(_gh([1, 2]), Blocked({}), _cands(2), out=out, log=lambda m: None)
    assert stats["stopped"] == "budget" and stats["decided"] == 0 and not out.exists()


def test_goldset_run_draft_keeps_what_was_decided_when_the_budget_stops(tmp_path):
    class Capped(dc.MockDecider):
        def classify(self, item):
            if len(self.asked) >= 1:
                raise BudgetExceeded("cap")
            return super().classify(item)

    out = tmp_path / "drafts.jsonl"
    table = {i: dc.Decision(status="ok", is_ai=False, type="기타") for i in (1, 2)}
    stats = gs.run_draft(_gh([1, 2]), Capped(table), _cands(2), out=out, log=lambda m: None)
    assert stats["stopped"] == "budget" and [r["repo_id"] for r in io.read_jsonl(out)] == [1]
