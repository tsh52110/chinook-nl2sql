"""Regression gate for the eval harness with a mocked LLM (no API calls).

Feeds the agent canned completions and asserts the pipeline classifies each
outcome correctly: correct / wrong_result / blocked / exec_error, plus EX math.
Runs the first 10 eval questions end-to-end with the gold SQL echoed back to
prove extraction -> guardrail -> execution -> result_eq scoring holds together.
"""

import json
from pathlib import Path

import pytest

from evals.run_eval import load_eval_set, score_item, summarize
from src import agent

REPO = Path(__file__).resolve().parent.parent
DB = str(REPO / "data" / "Chinook.db")
EVAL_SET = str(REPO / "evals" / "eval_set.jsonl")


def mock_llm(reply_fn):
    """Return a fake llm.complete that derives a reply from the user question."""

    def fake_complete(system, messages, max_tokens=1500):
        question = messages[0]["content"]
        return reply_fn(question)

    return fake_complete


@pytest.fixture
def eval_items():
    return load_eval_set(EVAL_SET)


def test_eval_set_is_50_questions(eval_items):
    assert len(eval_items) == 50
    assert {i["difficulty"] for i in eval_items} == {"easy", "medium", "hard"}
    assert len({i["id"] for i in eval_items}) == 50


def test_gold_sql_all_execute(eval_items):
    from src.executor import SQLiteExecutor

    ex = SQLiteExecutor(DB)
    for item in eval_items:
        r = ex.execute(item["gold_sql"])
        assert r.ok, f"gold q{item['id']} failed: {r.error}"


def test_subset_scores_100_when_model_echoes_gold(eval_items, monkeypatch):
    subset = eval_items[:10]
    gold_by_question = {i["question"]: i["gold_sql"] for i in subset}
    monkeypatch.setattr(
        agent.llm, "complete",
        mock_llm(lambda q: f"Using the schema.\n```sql\n{gold_by_question[q]}\n```"),
    )
    results = [score_item(i, DB, few_shot=False) for i in subset]
    summary = summarize(results)
    assert summary["ex"] == 100.0
    assert summary["outcomes"] == {"correct": 10}


def test_wrong_result_detected(eval_items, monkeypatch):
    item = eval_items[0]  # "how many tracks" -> gold 3503
    monkeypatch.setattr(agent.llm, "complete", mock_llm(lambda q: "```sql\nSELECT 42\n```"))
    r = score_item(item, DB, few_shot=False)
    assert r["outcome"] == "wrong_result"


def test_blocked_detected(eval_items, monkeypatch):
    item = eval_items[0]
    monkeypatch.setattr(
        agent.llm, "complete", mock_llm(lambda q: "```sql\nDROP TABLE Album\n```")
    )
    r = score_item(item, DB, few_shot=False)
    assert r["outcome"] == "blocked"


def test_exec_error_after_retries(eval_items, monkeypatch):
    item = eval_items[0]
    monkeypatch.setattr(
        agent.llm, "complete", mock_llm(lambda q: "```sql\nSELECT x FROM NoSuchTable\n```")
    )
    r = score_item(item, DB, few_shot=False)
    assert r["outcome"] == "exec_error"
    assert r["attempts"] == 3  # 1 initial + 2 self-correction retries


def test_order_matters_only_with_order_by():
    from evals.third_party.exec_eval import result_eq

    assert result_eq([(1,), (2,)], [(2,), (1,)], order_matters=False)
    assert not result_eq([(1,), (2,)], [(2,), (1,)], order_matters=True)
    # column permutation is tolerated
    assert result_eq([(1, "a")], [("a", 1)], order_matters=False)


def test_eval_set_jsonl_is_valid():
    with open(EVAL_SET) as f:
        for line in f:
            item = json.loads(line)
            assert set(item) == {"id", "difficulty", "question", "gold_sql"}
