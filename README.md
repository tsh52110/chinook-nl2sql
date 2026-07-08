# Chinook NL→SQL Agent — with a measured benchmark

Natural-language questions → guarded SQLite `SELECT`s → answers, over the public
[Chinook](https://github.com/lerocha/chinook-database) music-store database, with
**execution accuracy measured on a fixed 50-question benchmark** instead of claimed.

## Results

| Run | Model | Eval set | EX (overall) | Easy | Medium | Hard |
|---|---|---|---|---|---|---|
| Baseline (zero-shot) | `claude-haiku-4-5` | 50-q Chinook (full set, single run) | **98.0%** (49/50) | 100% (17/17) | 95% (19/20) | 100% (13/13) |
| + few-shot examples | `claude-haiku-4-5` | 50-q Chinook (full set, single run) | **100.0%** (50/50) | 100% (17/17) | 100% (20/20) | 100% (13/13) |

*EX = execution accuracy: the predicted query's result set matches the gold query's
result set under [test-suite-sql-eval](https://github.com/taoyds/test-suite-sql-eval)
semantics (row-order-insensitive unless the gold query has `ORDER BY`;
column-permutation-aware). Single-run numbers; the model is nondeterministic.*

The baseline's one miss (q25) cast `strftime('%Y', ...)` to INTEGER, so the year came
back as `2009` instead of `'2009'` — a type mismatch under strict EX. The few-shot
examples were written after this error analysis and are disjoint from the eval set.

## Architecture

```
question ──► prompt (schema CREATE TABLEs + rules [+ few-shot]) ──► claude-haiku-4-5
                                                                        │  CoT, then
                                                                        ▼  ```sql block
                                                                  extract SQL
                                                                        │
                                     ┌──────────────────────────────────┤
                                     ▼                                  │
                            sqlglot guardrail ── not a single SELECT ──►│ BLOCKED (never executed)
                                     │ single SELECT                    │
                                     ▼                                  │
                          SQLite (read-only, mode=ro)                   │
                                     │                                  │
                        error ───────┤ ok                               │
                          │          ▼                                  │
                          │     result table ──────────────────────────►│ answer
                          ▼
              feed error back to model (max 2 retries)
```

- **Agent** ([src/agent.py](src/agent.py)) — schema-aware system prompt (full
  `CREATE TABLE` dump), brief chain-of-thought (tables + joins) before a fenced
  ```` ```sql ```` block, self-correction loop feeding SQLite errors back
  (pattern from [premsql](https://github.com/premAI-io/premsql)'s
  execution-guided decoding, MIT).
- **Guardrail** ([src/guardrail.py](src/guardrail.py)) — sqlglot parses the SQL;
  only a **single SELECT** (incl. CTEs/UNIONs) passes. Writes, DDL, `PRAGMA`,
  `ATTACH`, and multi-statement payloads (`DROP TABLE albums; --`) are rejected
  with an explicit blocked state and never touch the database.
- **Defense in depth** ([src/executor.py](src/executor.py)) — the SQLite
  connection is opened read-only (`file:...?mode=ro`), so even a guardrail bypass
  cannot write. Adapted from premsql's `SQLiteExecutor` (MIT).
- **Scoring** ([evals/third_party/exec_eval.py](evals/third_party/exec_eval.py)) —
  `result_eq` vendored verbatim from
  [taoyds/test-suite-sql-eval](https://github.com/taoyds/test-suite-sql-eval)
  (Apache-2.0, license included alongside).

## Quick start

```bash
git clone https://github.com/tsh52110/chinook-nl2sql && cd chinook-nl2sql
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
```

Run the eval (spends ~$0.05 of Haiku credits per full pass):

```bash
python evals/run_eval.py                   # baseline prompt
python evals/run_eval.py --few-shot        # few-shot prompt
python evals/run_eval.py --validate-gold   # just verify all 50 gold queries execute
python evals/run_eval.py --few-shot --xlsx results.xlsx   # + xlsx report
```

Launch the UI:

```bash
streamlit run app.py
```

Type a question → see the generated SQL (reasoning collapsed above it) → the result
table. Ask for anything destructive and you get a visible **blocked by guardrail**
state instead of an execution.

**Deploy to Streamlit Community Cloud:** push the repo → [share.streamlit.io](https://share.streamlit.io)
→ new app → point at `app.py` → add `ANTHROPIC_API_KEY` under app Secrets.

## Eval methodology

- **Dataset:** `evals/eval_set.jsonl` — 50 hand-written `{question, gold_sql,
  difficulty}` pairs against Chinook v1.4.5 (17 easy / 20 medium / 13 hard). All
  gold queries are validated to execute (`--validate-gold`, also enforced in CI).
  Top-N questions were checked for rank-boundary ties so results are deterministic.
- **Metric:** execution accuracy only. Exact-string SQL match is not used.
- **Failure taxonomy:** `wrong_result` (ran, wrong rows), `exec_error` (still
  failing after 2 self-correction retries), `blocked` (guardrail), `no_sql`
  (no query produced).
- **Split discipline:** the 3 few-shot examples are hand-written and disjoint
  from the 50 eval questions.
- **Model:** `claude-haiku-4-5` (Anthropic SDK), chosen for cost. Swap in a
  stronger model with `NL2SQL_MODEL=claude-opus-4-8` — no code change.

**Known limitations:** result-set match can under-credit (formatting/type
differences count as wrong — that's the strict-EX convention) and over-credit
(a wrong query can coincidentally return matching rows). Numbers are single-run.

## CI

Every push: `ruff` + the full unit suite, including a **mocked-LLM regression
gate** that runs 10 eval questions through extraction → guardrail → read-only
execution → `result_eq` scoring with canned completions (zero API cost). The
live 50-question eval is a separate manually-dispatched job (`Actions → CI →
Run workflow → live_eval`) needing an `ANTHROPIC_API_KEY` repo secret.

## Licenses & credits

- This repo: [MIT](LICENSE). Chinook DB © Luis Rocha, MIT-like license.
- `evals/third_party/exec_eval.py`: verbatim from taoyds/test-suite-sql-eval,
  Apache-2.0 ([license](evals/third_party/LICENSE-APACHE)).
- `src/executor.py` + the self-correction pattern: adapted from premAI-io/premsql, MIT.
- Schema-in-prompt approach influenced by [vanna-ai/vanna](https://github.com/vanna-ai/vanna)
  (archived March 2026 — studied for its RAG-schema pattern, not a dependency).
