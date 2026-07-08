"""NL -> SQL agent: schema-aware prompt, CoT, fenced-SQL extraction, self-correction.

The self-correction loop (feed the SQLite error back and regenerate, bounded
retries) follows the execution_guided_decoding pattern in premAI-io/premsql
(premsql/generators/base.py + ERROR_HANDLING_PROMPT in premsql/prompts.py, MIT).
"""

import re
from dataclasses import dataclass, field
from functools import lru_cache

from src import llm
from src.executor import ExecutionResult, SQLiteExecutor
from src.guardrail import check_sql
from src.schema import get_schema

MAX_RETRIES = 2  # regeneration attempts after a failed execution

SYSTEM_TEMPLATE = """You are an expert SQLite analyst for the Chinook music-store database.

Database schema:

{schema}

Answer the user's question by writing ONE SQLite SELECT query.

Rules:
- First, briefly reason step by step: name the tables you need and how they join.
- Then output exactly one SQL query in a fenced code block: ```sql ... ```
- SELECT statements only. Never write INSERT, UPDATE, DELETE, DROP, or any DDL.
- Use only tables and columns that exist in the schema above.
- Return only the columns needed to answer the question.
{few_shot_block}"""

# Hand-written examples, disjoint from the 50-question eval set.
# Empty at baseline; populated in the improvement pass (see README).
FEW_SHOT_EXAMPLES: list[dict] = []

ERROR_FEEDBACK_TEMPLATE = """Your SQL failed to execute.

Query:
{sql}

SQLite error:
{error}

Review the schema and the original question, then output a corrected SQLite SELECT
query in a ```sql fenced block. Use correct table and column names and do not
introduce new errors."""


@dataclass
class AgentResult:
    status: str  # "ok" | "error" | "blocked" | "no_sql"
    sql: str | None = None
    cot: str = ""
    execution: ExecutionResult | None = None
    attempts: int = 0
    blocked_reason: str | None = None
    transcript: list = field(default_factory=list)


def extract_sql(text: str) -> str | None:
    """Pull the last ```sql fenced block out of a model response."""
    blocks = re.findall(r"```sql\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if not blocks:
        blocks = re.findall(r"```\s*(SELECT\b.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if not blocks:
        return None
    return blocks[-1].strip().rstrip(";").strip()


@lru_cache(maxsize=4)
def _system_prompt(db_path: str, few_shot: bool) -> str:
    few_shot_block = ""
    if few_shot and FEW_SHOT_EXAMPLES:
        examples = "\n\n".join(
            f"Example question: {ex['question']}\n```sql\n{ex['sql']}\n```"
            for ex in FEW_SHOT_EXAMPLES
        )
        few_shot_block = f"\nExamples of correct queries for this database:\n\n{examples}\n"
    return SYSTEM_TEMPLATE.format(schema=get_schema(db_path), few_shot_block=few_shot_block)


def answer(question: str, db_path: str, few_shot: bool = False) -> AgentResult:
    """Generate SQL for a question, execute it, self-correct on execution errors."""
    system = _system_prompt(db_path, few_shot)
    executor = SQLiteExecutor(db_path)
    messages = [{"role": "user", "content": question}]
    result = AgentResult(status="no_sql")

    for attempt in range(1 + MAX_RETRIES):
        result.attempts = attempt + 1
        completion = llm.complete(system, messages)
        result.transcript.append(completion)
        sql = extract_sql(sql_text := completion)
        result.cot = re.split(r"```", sql_text)[0].strip()
        if sql is None:
            result.status = "no_sql"
            return result
        result.sql = sql

        verdict = check_sql(sql)
        if not verdict.allowed:
            result.status = "blocked"
            result.blocked_reason = verdict.reason
            return result

        execution = executor.execute(sql)
        result.execution = execution
        if execution.ok:
            result.status = "ok"
            return result

        result.status = "error"
        messages.append({"role": "assistant", "content": completion})
        messages.append(
            {"role": "user", "content": ERROR_FEEDBACK_TEMPLATE.format(sql=sql, error=execution.error)}
        )

    return result
