import asyncio
import json

import pytest

import app.db.session as session_mod
from app.core.config import Settings
from app.evals import cli, runner
from app.evals.dataset import Dataset, Document, Question, load_dataset, validate
from app.evals.env import isolate
from app.evals.experiments import DEFAULT_GRID, render_markdown, run_grid
from app.evals.metrics import (
    contains, fact_hits, first_gold_rank, gold_recall, hit, norm, percentile, rate,
    reciprocal_rank, wilson_interval,
)
from app.evals.report import compare_markdown, write_reports
from app.evals.retrieval import RetrievalConfig, build_store, evaluate_retrieval, fill_store
from app.evals.runner import ResultCache, run_system, score_question, select_questions, summarize
from app.evals.systems import AgentOpsSystem, ExtractiveSystem, SystemResult
from app.graph import nodes
from app.providers.base import ProviderError
from app.retrieval.store import get_store
from tests.helpers import run

DS = load_dataset()
CFG = RetrievalConfig("test")


def q(id="x1", type="direct", question="How much does Pro cost?", gold=("29 dollars",), facts=(("29 dollars",),)):
    answerable = type in ("direct", "paraphrase")
    return Question(id, question, type, answerable, tuple(gold) if answerable else (), tuple(facts) if answerable else ())


# ---------------- metrics ----------------
def test_normalisation_ignores_case_markdown_and_fancy_punctuation():
    assert norm("  **30 Days**\n of “notice” ") == '30 days of "notice"'
    assert contains("You get **30 days**.", "30 days")
    assert not contains("thirty days", "30 days")


def test_hit_rank_and_recall():
    texts = ["nothing here", "Refunds within 14 days of purchase", "other"]
    assert hit(texts, ["14 days"]) and not hit(texts, ["30 days"])
    assert first_gold_rank(texts, ["14 days"]) == 2 and first_gold_rank(texts, ["x"]) is None
    assert reciprocal_rank(2) == 0.5 and reciprocal_rank(None) == 0.0
    assert gold_recall(texts, ["14 days", "missing"]) == 0.5


def test_fact_hits_accepts_any_wording_of_each_fact():
    facts = [["30 days", "thirty days"], ["credit"]]
    assert fact_hits("You get a **credit** within thirty days.", facts) == (2, 2)
    assert fact_hits("You get a credit.", facts) == (1, 2)


def test_wilson_interval_matches_known_values():
    low, high = wilson_interval(0, 10)
    assert low == 0.0 and high == pytest.approx(0.2775, abs=1e-3)
    low, high = wilson_interval(10, 10)
    assert low == pytest.approx(0.7225, abs=1e-3) and high == 1.0
    low, high = wilson_interval(5, 10)
    assert (low, high) == (pytest.approx(0.2366, abs=1e-3), pytest.approx(0.7634, abs=1e-3))
    assert wilson_interval(0, 0) == (0.0, 1.0)
    # more data, narrower interval
    assert wilson_interval(500, 1000)[1] - wilson_interval(500, 1000)[0] < 0.07


def test_percentile_and_rate():
    assert percentile([1, 2, 3, 4], 50) == 2.5 and percentile([], 50) is None
    assert percentile([1, 2, 3, 4], 100) == 4
    r = rate(3, 4)
    assert r["value"] == 0.75 and r["k"] == 3 and r["n"] == 4 and r["ci"][0] < 0.75 < r["ci"][1]
    assert rate(0, 0)["value"] is None


# ---------------- dataset ----------------
def test_shipped_dataset_is_valid_and_has_the_documented_shape():
    assert validate(DS) == []
    assert len(DS.documents) == 20 and len(DS.questions) == 44
    kinds = {t: sum(x.type == t for x in DS.questions) for t in ("direct", "paraphrase", "off_topic", "near_miss")}
    assert kinds == {"direct": 16, "paraphrase": 8, "off_topic": 8, "near_miss": 12}
    assert sum(x.answerable for x in DS.questions) == 24
    assert load_dataset().sha256 == DS.sha256  # stable fingerprint


def test_validation_catches_mistakes():
    doc = Document("a.md", "The Pro plan costs 29 dollars per month.")
    bad = Dataset("t", "", (doc,), (
        q("a1"),
        q("a1"),  # duplicate id
        q("a2", gold=("a price that is not in the corpus",)),
        q("a3", facts=(("seventy",),)),  # wording not in the corpus
        Question("a4", "Why?", "direct", True),  # answerable without evidence or facts
        Question("a5", "Why?", "off_topic", True),  # type and flag disagree
        Question("a6", "Why?", "off_topic", False, ("29 dollars",), ()),  # unanswerable with evidence
        Question("a7", "Why?", "mystery", False),
    ), "sha")
    text = "\n".join(validate(bad))
    for expected in ("duplicate id", "gold evidence not found", "none of these wordings", "needs gold_evidence",
                     "does not match type", "must not have gold", "unknown type"):
        assert expected in text, expected


# ---------------- retrieval evaluation ----------------
def test_search_beats_random_by_a_wide_margin_on_the_shipped_dataset():
    store = build_store(DS, CFG)
    result = evaluate_retrieval(store, DS, CFG)
    a, u = result["answerable"], result["unanswerable"]
    assert a["all"]["n"] == 24 and u["all"]["n"] == 20
    assert a["all"]["system_hit"]["value"] >= 0.85
    assert a["all"]["system_hit"]["value"] > 3 * a["all"]["random_hit"]
    assert a["direct"]["system_hit"]["value"] >= a["paraphrase"]["system_hit"]["value"]
    assert u["off_topic"]["no_evidence_first"]["value"] == 1.0
    assert result["n_chunks"] == len(store._chunks) > 20


def test_experiment_grid_changes_one_thing_at_a_time_and_renders():
    results = run_grid(DS)
    assert len(results) == len(DEFAULT_GRID) == 7
    chunks = {r["config"]["name"]: r["n_chunks"] for r in results}
    assert chunks["smaller chunks (500/100)"] > chunks["baseline (current defaults)"] > chunks["larger chunks (1500/200)"]
    table = render_markdown(DS, results)
    assert "baseline (current defaults)" in table and "random chunks" in table and "Hit@k" in table


def test_evaluation_is_deterministic():
    store = build_store(DS, CFG)
    first = evaluate_retrieval(store, DS, CFG)
    second = evaluate_retrieval(build_store(DS, CFG), DS, CFG)
    assert first == second


# ---------------- isolation ----------------
def test_isolate_switches_off_the_database_and_tracing(monkeypatch):
    monkeypatch.setattr(session_mod, "get_database_url", lambda: "postgresql://real:secret@prod/db")
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    assert session_mod.db_enabled() is True
    isolate()
    assert session_mod.db_enabled() is False
    import os
    assert os.environ["LANGSMITH_TRACING"] == "false"


# ---------------- systems ----------------
def test_extractive_baseline_answers_direct_questions_and_refuses_off_topic_ones():
    store = build_store(DS, CFG)
    system = ExtractiveSystem(store, CFG)
    good = run(system.answer("How much does the Pro plan cost per month?"))
    assert not good.abstained and "29 dollars" in good.answer and good.llm_calls == 0 and good.chunk_ids
    refused = run(system.answer("What is the capital of Australia?"))
    assert refused.abstained and refused.chunk_ids == [] and refused.retrieval_attempts == 2


class FakeModel:
    """Stands in for the model: answers from the passage, rewrites queries, can refuse."""

    def __init__(self, answer="The Pro plan costs 29 dollars per month per workspace [1]."):
        self.answer, self.prompts = answer, []

    async def __call__(self, prompt, **kwargs):
        self.prompts.append(prompt)
        text = "football world cup winner" if "Rewrite the question" in prompt else self.answer
        return {"content": text, "model": "fake", "provider": "openrouter"}


@pytest.fixture
def agent_store():
    get_store.cache_clear()
    yield fill_store(get_store(), DS, CFG)
    get_store.cache_clear()


def test_agentops_system_runs_the_real_graph_and_counts_model_calls(agent_store, monkeypatch):
    monkeypatch.setattr(nodes, "complete", FakeModel())
    result = run(AgentOpsSystem("openrouter").answer("How much does the Pro plan cost per month?"))
    assert not result.abstained and result.llm_calls == 1 and result.chunk_ids and result.provider == "openrouter"
    assert result.steps == ["validate", "retrieve", "generate", "verify"]

    refused = run(AgentOpsSystem("openrouter").answer("Who won the football World Cup in 2018?"))
    assert refused.abstained and refused.llm_calls == 1  # one query rewrite, no answer call


def test_agentops_system_reports_provider_errors_instead_of_raising(agent_store, monkeypatch):
    async def failing(prompt, **kwargs):
        raise ProviderError("rate_limited", "slow down")

    monkeypatch.setattr(nodes, "complete", failing)
    result = run(AgentOpsSystem("groq").answer("How much does the Pro plan cost per month?"))
    assert result.error == "rate_limited" and result.provider == "groq"


# ---------------- scoring ----------------
@pytest.fixture
def store():
    return build_store(DS, CFG)


def chunk_with(store, text):
    return next(cid for cid, c in store._chunks.items() if text in c.text)


def test_scoring_covers_every_outcome(store):
    pro = chunk_with(store, "costs 29 dollars")
    other = chunk_with(store, "Invoices are issued")
    question = q(facts=(("29 dollars",),), gold=("costs 29 dollars",))

    correct = score_question(question, SystemResult(answer="It costs **29 dollars** [1]", chunk_ids=[pro]), store)
    assert correct["status"] == "correct" and correct["cited_gold"] and correct["fact_recall"] == 1.0

    wrong_source = score_question(question, SystemResult(answer="It costs 29 dollars [1]", chunk_ids=[other]), store)
    assert wrong_source["status"] == "correct" and wrong_source["cited_gold"] is False  # right answer, wrong citation

    assert score_question(question, SystemResult(answer="It is cheap [1]", chunk_ids=[pro]), store)["status"] == "incorrect"
    assert score_question(question, SystemResult(abstained=True), store)["status"] == "false_abstention"
    assert score_question(question, SystemResult(error="timeout"), store)["status"] == "error"

    off = q("o1", "off_topic", "What is the capital of Australia?")
    assert score_question(off, SystemResult(abstained=True), store)["status"] == "correct_abstention"
    assert score_question(off, SystemResult(answer="Canberra"), store)["status"] == "unsupported_answer"


def test_summary_rates_exclude_errors_and_are_computed_as_defined():
    def row(id, type, status, **extra):
        return {"id": id, "type": type, "answerable": type in ("direct", "paraphrase"), "status": status, "question": id, **extra}

    scored = [
        row("a", "direct", "correct", cited_gold=True),
        row("b", "direct", "correct", cited_gold=False),
        row("c", "paraphrase", "incorrect", cited_gold=True),
        row("d", "paraphrase", "false_abstention"),
        row("e", "off_topic", "correct_abstention"),
        row("f", "near_miss", "correct_abstention"),
        row("g", "near_miss", "unsupported_answer"),
        row("h", "near_miss", "error", detail="rate_limited"),
    ]
    results = [SystemResult(latency_s=s, llm_calls=c) for s, c in ((1, 1), (2, 1), (3, 2), (4, 1), (1, 1), (2, 1), (3, 1), (9, 0))]
    s = summarize(scored, results)
    assert s["n_errors"] == 1 and s["error_kinds"] == {"rate_limited": 1}
    assert (s["answerable_accuracy"]["k"], s["answerable_accuracy"]["n"]) == (2, 4)
    assert (s["false_abstention_rate"]["k"], s["false_abstention_rate"]["n"]) == (1, 4)
    assert (s["abstention_recall"]["k"], s["abstention_recall"]["n"]) == (2, 3)
    assert (s["abstention_precision"]["k"], s["abstention_precision"]["n"]) == (2, 3)  # 2 right refusals, 1 wrong
    assert (s["decision_accuracy"]["k"], s["decision_accuracy"]["n"]) == (4, 7)
    assert (s["citation_gold_rate"]["k"], s["citation_gold_rate"]["n"]) == (2, 3)
    assert s["by_type"]["near_miss"]["n"] == 2  # the error is not counted
    assert s["latency_p50_s"] == 2.5 and s["llm_calls_mean"] == pytest.approx(8 / 8)
    assert {f["id"] for f in s["failures"]} == {"c", "d", "g", "h"}


# ---------------- running, sampling, cache ----------------
def test_a_small_sample_still_contains_every_question_type():
    types = {x.type for x in select_questions(DS, 8)}
    assert types == {"direct", "paraphrase", "off_topic", "near_miss"}
    assert len(select_questions(DS, 8)) == 8 and len(select_questions(DS, None)) == 44


class CountingSystem:
    name, uses_llm, provider = "counting", True, "x"

    def __init__(self, fail_first=False):
        self.calls, self.fail_first = 0, fail_first

    async def answer(self, question):
        self.calls += 1
        if self.fail_first and self.calls == 1:
            return SystemResult(error="rate_limited")
        return SystemResult(answer="Not found.", abstained=True, latency_s=0.1)


def test_cache_prevents_repeat_spending_and_respects_config_and_errors(tmp_path, store):
    cache_file = tmp_path / "cache.jsonl"
    config = {"model": "a"}

    first = CountingSystem()
    run(run_system(first, DS, store, config=config, limit=6, cache=ResultCache(cache_file)))
    assert first.calls == 6

    second = CountingSystem()  # same settings: everything comes from the cache (and survives a restart)
    _, _, cached = run(run_system(second, DS, store, config=config, limit=6, cache=ResultCache(cache_file)))
    assert second.calls == 0 and cached == 6

    third = CountingSystem()  # a different model must NOT reuse the answers
    run(run_system(third, DS, store, config={"model": "b"}, limit=6, cache=ResultCache(cache_file)))
    assert third.calls == 6

    flaky_file = tmp_path / "flaky.jsonl"  # an error is not cached, so the next run retries it
    flaky = CountingSystem(fail_first=True)
    run(run_system(flaky, DS, store, config=config, limit=3, cache=ResultCache(flaky_file)))
    retry = CountingSystem()
    run(run_system(retry, DS, store, config=config, limit=3, cache=ResultCache(flaky_file)))
    assert retry.calls == 1


def test_delay_is_applied_between_model_questions_only(store, monkeypatch):
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(runner.asyncio, "sleep", fake_sleep)
    run(run_system(CountingSystem(), DS, store, config={}, limit=4, delay=3.0))
    assert sleeps == [3.0, 3.0, 3.0]  # between 4 questions, not after the last
    sleeps.clear()
    run(run_system(ExtractiveSystem(store, CFG), DS, store, config={}, limit=4, delay=3.0))
    assert sleeps == []  # no model, no waiting


def test_a_run_of_the_baseline_is_reproducible(store):
    def once():
        system = ExtractiveSystem(store, CFG)
        scored, results, _ = run(run_system(system, DS, store, config={}))
        s = summarize(scored, results)
        s.pop("latency_p50_s"), s.pop("latency_p95_s")
        return s

    assert once() == once()


# ---------------- reports and command line ----------------
def meta(label="", system="agentops"):
    return {"system": system, "provider": "groq", "model": "m1", "label": label, "timestamp": "2026-10-22 10:00",
            "dataset": {"name": DS.name, "sha256": DS.sha256}, "config": {"chunk_size": 900, "overlap": 150, "top_k": 4, "min_coverage": 0.34}, "cached": 0}


def test_reports_are_written_and_comparable(tmp_path, store):
    scored, results, _ = run(run_system(ExtractiveSystem(store, CFG), DS, store, config={}))
    summary = summarize(scored, results)
    json_path, md_path = write_reports(tmp_path, "t", meta("baseline"), summary, scored, [r.to_dict() for r in results])
    data = json.loads(json_path.read_text())
    assert data["summary"]["n_questions"] == 44 and len(data["questions"]) == 44
    assert "Evaluation report" in md_path.read_text() and "Where it went wrong" in md_path.read_text()

    other = {"meta": meta("candidate"), "summary": summary}
    table = compare_markdown([data, other])
    assert "baseline" in table and "candidate" in table and "Abstention recall" in table


def test_cli_validate_retrieval_and_baseline(tmp_path, capsys):
    assert cli.main(["validate"]) == 0
    assert "is valid" in capsys.readouterr().out
    assert cli.main(["retrieval", "--out", str(tmp_path)]) == 0
    assert list(tmp_path.glob("*-retrieval.md")) and list(tmp_path.glob("*-retrieval.json"))
    assert cli.main(["run", "--system", "extractive", "--out", str(tmp_path)]) == 0
    assert list(tmp_path.glob("*extractive*.md"))
    reports = sorted(tmp_path.glob("*extractive*.json"))
    assert cli.main(["compare", str(reports[0]), str(reports[0])]) == 0
    assert "Comparison" in capsys.readouterr().out


def test_cli_refuses_to_run_a_provider_without_a_key(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "get_settings", lambda: Settings(_env_file=None))
    assert cli.main(["run", "--system", "agentops", "--provider", "groq", "--out", str(tmp_path)]) == 2
    assert "GROQ_API_KEY" in capsys.readouterr().out


def test_cli_runs_the_real_pipeline_with_a_provider_and_restores_settings(tmp_path, monkeypatch, capsys, use):
    settings = use(Settings(_env_file=None, groq_api_key="k", admin_token="t"))
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr("app.services.chat_service.get_settings", lambda: settings)
    monkeypatch.setattr(nodes, "complete", FakeModel())

    code = cli.main(["run", "--system", "agentops", "--provider", "groq", "--limit", "8", "--no-cache", "--out", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0 and "Evaluating agentops with groq" in out and "PASS" in out
    assert (settings.llm_provider, settings.rag_top_k, settings.max_documents) == ("openrouter", 4, 10)  # settings restored
    report = json.loads(next(tmp_path.glob("*groq*.json")).read_text())
    assert report["meta"]["provider"] == "groq" and report["summary"]["n_questions"] == 8
