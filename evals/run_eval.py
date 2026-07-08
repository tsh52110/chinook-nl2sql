"""Execution-accuracy (EX) eval runner.

For each {question, gold_sql} pair: run the agent, execute both predicted and
gold SQL against Chinook, and score a match with the vendored
test-suite-sql-eval result_eq (row/column permutation-aware; row order only
matters when the gold query has an ORDER BY — same convention as upstream).

Usage:
  python evals/run_eval.py                        # full 50-question run
  python evals/run_eval.py --few-shot             # with few-shot prompt
  python evals/run_eval.py --limit 10             # first N questions
  python evals/run_eval.py --validate-gold        # only check gold SQL executes
  python evals/run_eval.py --xlsx results.xlsx    # also write an xlsx report
"""

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from evals.third_party.exec_eval import result_eq  # noqa: E402
from src.agent import answer  # noqa: E402
from src.executor import SQLiteExecutor  # noqa: E402


def load_eval_set(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def validate_gold(items: list[dict], db_path: str) -> bool:
    executor = SQLiteExecutor(db_path)
    ok = True
    for item in items:
        r = executor.execute(item["gold_sql"])
        if not r.ok:
            print(f"GOLD FAILED  q{item['id']}: {r.error}")
            ok = False
        elif not r.rows:
            print(f"GOLD EMPTY   q{item['id']} (allowed, but check intent)")
    print(f"gold validation: {'OK' if ok else 'FAILED'} ({len(items)} queries)")
    return ok


def score_item(item: dict, db_path: str, few_shot: bool) -> dict:
    executor = SQLiteExecutor(db_path)
    gold = executor.execute(item["gold_sql"])
    if not gold.ok:
        raise RuntimeError(f"gold SQL for q{item['id']} failed: {gold.error}")

    start = time.time()
    result = answer(item["question"], db_path, few_shot=few_shot)
    elapsed = time.time() - start

    if result.status == "blocked":
        outcome = "blocked"
    elif result.status == "no_sql":
        outcome = "no_sql"
    elif result.status == "error":
        outcome = "exec_error"
    else:
        order_matters = "order by" in item["gold_sql"].lower()
        match = result_eq(gold.rows, result.execution.rows, order_matters=order_matters)
        outcome = "correct" if match else "wrong_result"

    return {
        "id": item["id"],
        "difficulty": item["difficulty"],
        "question": item["question"],
        "gold_sql": item["gold_sql"],
        "predicted_sql": result.sql,
        "outcome": outcome,
        "attempts": result.attempts,
        "latency_s": round(elapsed, 2),
    }


def summarize(results: list[dict]) -> dict:
    total = len(results)
    correct = sum(1 for r in results if r["outcome"] == "correct")
    by_difficulty = {}
    for diff in ("easy", "medium", "hard"):
        subset = [r for r in results if r["difficulty"] == diff]
        if subset:
            c = sum(1 for r in subset if r["outcome"] == "correct")
            by_difficulty[diff] = {"n": len(subset), "correct": c, "ex": round(100 * c / len(subset), 1)}
    return {
        "n": total,
        "correct": correct,
        "ex": round(100 * correct / total, 1) if total else 0.0,
        "by_difficulty": by_difficulty,
        "outcomes": dict(Counter(r["outcome"] for r in results)),
    }


def write_xlsx(results: list[dict], summary: dict, path: str, label: str) -> None:
    import pandas as pd

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        rows = [{"run": label, "metric": "EX %", "value": summary["ex"]},
                {"run": label, "metric": "correct", "value": summary["correct"]},
                {"run": label, "metric": "n", "value": summary["n"]}]
        for diff, s in summary["by_difficulty"].items():
            rows.append({"run": label, "metric": f"EX % ({diff})", "value": s["ex"]})
        for outcome, n in sorted(summary["outcomes"].items()):
            rows.append({"run": label, "metric": f"count: {outcome}", "value": n})
        pd.DataFrame(rows).to_excel(writer, sheet_name="summary", index=False)
        pd.DataFrame(results).to_excel(writer, sheet_name="per_question", index=False)
    print(f"wrote {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(REPO_ROOT / "data" / "Chinook.db"))
    parser.add_argument("--eval-set", default=str(REPO_ROOT / "evals" / "eval_set.jsonl"))
    parser.add_argument("--few-shot", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", default=None, help="write per-question results jsonl here")
    parser.add_argument("--xlsx", default=None, help="write an xlsx report here")
    parser.add_argument("--validate-gold", action="store_true")
    args = parser.parse_args()

    items = load_eval_set(args.eval_set)
    if args.limit:
        items = items[: args.limit]

    if args.validate_gold:
        return 0 if validate_gold(items, args.db) else 1

    label = "few-shot" if args.few_shot else "baseline"
    results = []
    for item in items:
        r = score_item(item, args.db, args.few_shot)
        results.append(r)
        print(f"q{r['id']:>2} [{r['difficulty']:<6}] {r['outcome']:<12} ({r['attempts']} attempt(s), {r['latency_s']}s)")

    summary = summarize(results)
    print(f"\n== {label} ==")
    print(json.dumps(summary, indent=2))

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w") as f:
            for r in results:
                f.write(json.dumps(r) + "\n")
    if args.xlsx:
        write_xlsx(results, summary, args.xlsx, label)
    return 0


if __name__ == "__main__":
    sys.exit(main())
