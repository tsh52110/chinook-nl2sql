# PRD — Chinook NL→SQL Agent with Measured Execution Accuracy

**Status:** v1.0 · **Owner:** Taha Hussain · **Last updated:** 2026-07-08

## Problem

Natural-language-to-SQL demos are easy to build and hard to trust. Most show a chatbot that
emits SQL with no safety layer and no measured accuracy — "works great" with zero evidence.
Anyone evaluating such a system (a hiring manager, a teammate, a future self) has no way to
know how often it is actually right, or whether it can be pointed at a database without risk
of destructive writes.

## Objective & Success Metric

Build a minimal, end-to-end text-to-SQL agent over the public Chinook SQLite database whose
quality is a **measured number, not a claim**.

- **Primary metric:** Execution accuracy (EX) — the % of questions where the generated SQL's
  result set matches the gold SQL's result set (test-suite-sql-eval semantics: row/column
  permutation-invariant match) — on a fixed, hand-written **50-question Chinook benchmark**.
- **Success:** baseline EX measured and reported; at least one prompt improvement (few-shot
  examples) applied with before/after EX published in the README, naming the exact model and
  dataset split.
- **Secondary:** guardrail blocks 100% of non-SELECT statements in unit tests.

## Functional Requirements

1. **Agent** (`src/agent.py`): schema-aware system prompt (full `CREATE TABLE` dump),
   chain-of-thought that lists relevant tables/joins before emitting SQL in a fenced block;
   SQL parsed from the block; self-correction loop (max 2 retries) that feeds SQLite execution
   errors back to the model.
2. **Guardrail** (`src/guardrail.py`): sqlglot-parsed validation; only a **single SELECT**
   statement may reach the database. INSERT/UPDATE/DELETE/DROP, any DDL, multi-statement
   payloads, and unparseable SQL are rejected with an explicit `blocked` state. Defense in
   depth: the executor opens SQLite in read-only mode (`mode=ro`), so even a guardrail bypass
   cannot write.
3. **Benchmark** (`evals/`): 50 `{question, gold_sql, difficulty}` pairs over Chinook;
   runner computes EX via vendored test-suite-sql-eval `result_eq`, with breakdowns by
   difficulty (easy/medium/hard) and failure type (syntax error / wrong result / blocked).
4. **UI** (`app.py`): Streamlit app — question box → generated SQL (CoT collapsed) →
   result table → visible "blocked by guardrail" state. Deployable to Streamlit Community
   Cloud.
5. **CI**: lint + unit tests + a small fixed eval subset with a **mocked** LLM as a regression
   gate on every push; live-LLM eval behind manual `workflow_dispatch` only.

## Non-Functional Requirements

- **Safety:** no non-SELECT statement ever executes against the DB, including in tests
  (read-only connection + guardrail).
- **Latency:** single question answered in < 10 s p50 with the dev model (excluding retries).
- **Reproducibility:** fresh clone + `pip install -r requirements.txt` + `ANTHROPIC_API_KEY`
  runs the eval and launches the UI from README instructions alone. Eval set and model are
  pinned; results reported only from actual runs.
- **Cost:** dev/eval model is `claude-haiku-4-5` (cheap); the README documents the single
  constant to change to swap in a stronger model (e.g. `claude-opus-4-8`).
- **Licensing:** MIT for this repo; vendored code labeled with source + license
  (premsql — MIT; test-suite-sql-eval — Apache-2.0). Public data only (Chinook).

## Scope / Out of Scope

**In:** single SQLite DB (Chinook), single-turn Q→SQL→answer, EX benchmark, few-shot
improvement pass, Streamlit UI, CI.

**Out:** multi-database routing, RAG over schema docs (Vanna-style schema retrieval noted as
future work only), conversation memory, fine-tuning, non-SQLite dialects, auth/multi-tenancy,
semantic-equivalence scoring beyond result-set match.

## Risks

| Risk | Mitigation |
|---|---|
| Gold SQL itself wrong | Every gold query executed + eyeballed during set construction; validation script asserts all 50 execute |
| EX overstates quality (result match ≠ intent match) | Documented limitation; permutation-aware `result_eq` reduces false negatives |
| LLM nondeterminism makes numbers unstable | Temperature-free calls where supported; eval set fixed; model pinned; single-run numbers labeled as such |
| CI cost blowup | Mocked LLM in CI; live eval manual-dispatch only |
| Benchmark leakage into prompt | Few-shot examples are hand-written and disjoint from the 50 eval questions |
