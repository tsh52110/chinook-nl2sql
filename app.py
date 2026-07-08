"""Streamlit UI for the Chinook NL->SQL agent.

Run locally:  streamlit run app.py
Deploy:       push to GitHub -> share.streamlit.io -> point at app.py, and set
              ANTHROPIC_API_KEY in the app's Secrets.
"""

import os
from pathlib import Path

import pandas as pd
import streamlit as st

# Streamlit Community Cloud provides secrets via st.secrets; mirror into env
# so the anthropic client picks it up.
try:
    if "ANTHROPIC_API_KEY" in st.secrets and not os.environ.get("ANTHROPIC_API_KEY"):
        os.environ["ANTHROPIC_API_KEY"] = st.secrets["ANTHROPIC_API_KEY"]
except Exception:
    pass  # no secrets.toml locally — env var is used instead

from src.agent import answer  # noqa: E402
from src.llm import model_name  # noqa: E402

DB_PATH = str(Path(__file__).parent / "data" / "Chinook.db")

st.set_page_config(page_title="Chinook NL->SQL", page_icon="🎵", layout="wide")
st.title("🎵 Ask the Chinook music store")
st.caption(
    f"Natural language → SQL over the Chinook SQLite DB · model: `{model_name()}` · "
    "read-only, single-SELECT guardrail enforced"
)

with st.sidebar:
    st.header("About")
    st.markdown(
        "- Generates **one SQLite SELECT** per question\n"
        "- **Guardrail:** sqlglot parse — anything that isn't a single SELECT is blocked\n"
        "- **Defense in depth:** the DB connection is opened read-only\n"
        "- Self-corrects on execution errors (max 2 retries)\n"
    )
    few_shot = st.toggle("Few-shot prompt", value=True, help="Include few-shot examples (the setting that scored higher on the benchmark)")
    st.markdown("[Repo & benchmark methodology](https://github.com/tsh52110/chinook-nl2sql)")

question = st.text_input(
    "Ask a question about the music store",
    placeholder="e.g. Which 3 artists have generated the most revenue?",
)

if question:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        st.error("ANTHROPIC_API_KEY is not set (env var or Streamlit secret).")
        st.stop()

    with st.spinner("Generating SQL..."):
        result = answer(question, DB_PATH, few_shot=few_shot)

    if result.cot:
        with st.expander("Model reasoning (chain of thought)", expanded=False):
            st.markdown(result.cot)

    if result.status == "blocked":
        st.error(
            f"🛑 **Blocked by guardrail** — the generated statement is not a single "
            f"SELECT and was never executed.\n\nReason: `{result.blocked_reason}`"
        )
        st.code(result.sql or "", language="sql")
    elif result.status == "no_sql":
        st.warning("The model did not produce a SQL query for this question.")
        if result.transcript:
            st.markdown(result.transcript[-1])
    elif result.status == "error":
        st.error(f"Query failed after {result.attempts} attempt(s): `{result.execution.error}`")
        st.code(result.sql, language="sql")
    else:
        st.subheader("Generated SQL")
        st.code(result.sql, language="sql")
        rows = result.execution.rows
        st.subheader(f"Result ({len(rows)} row{'s' if len(rows) != 1 else ''})")
        if rows:
            st.dataframe(
                pd.DataFrame(rows, columns=result.execution.columns or None),
                use_container_width=True,
            )
        else:
            st.info("Query ran successfully but returned no rows.")
        st.caption(
            f"{result.attempts} attempt(s) · executed in {result.execution.execution_time:.2f}s"
        )
