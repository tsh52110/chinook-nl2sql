"""Thin Anthropic client wrapper.

Dev/eval model is claude-haiku-4-5 (cheap). To swap in a stronger model,
set NL2SQL_MODEL=claude-opus-4-8 (or edit DEFAULT_MODEL) — no other change needed.
"""

import os

import anthropic

DEFAULT_MODEL = "claude-haiku-4-5"

_client = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    return _client


def model_name() -> str:
    return os.environ.get("NL2SQL_MODEL", DEFAULT_MODEL)


def complete(system: str, messages: list[dict], max_tokens: int = 1500) -> str:
    response = get_client().messages.create(
        model=model_name(),
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    return "".join(block.text for block in response.content if block.type == "text")
