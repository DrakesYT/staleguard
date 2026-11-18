"""Per-request usage accounting (tokens, cost, provider routing, searches).

A pipeline run sets a fresh Usage in a ContextVar; every LLM/search call adds to it.
asyncio tasks inherit the context, so concurrent claim checks all report into the same object.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

from .models import Usage

_current: ContextVar[Usage | None] = ContextVar("usage", default=None)

# Approximate list prices, USD per 1M tokens (input, output). Estimates for the cost meter only.
PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-pro": (1.25, 10.00),
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "llama-3.1-8b-instant": (0.05, 0.08),
    "claude-3-5-haiku-latest": (0.80, 4.00),
}


def current() -> Usage | None:
    return _current.get()


@contextmanager
def track():
    usage = Usage()
    token = _current.set(usage)
    try:
        yield usage
    finally:
        _current.reset(token)


def record_llm(provider: str, model: str, prompt_toks: int, completion_toks: int, is_fallback: bool) -> None:
    u = _current.get()
    if u is None:
        return
    u.llm_calls += 1
    u.prompt_tokens += prompt_toks
    u.completion_tokens += completion_toks
    if is_fallback:
        u.fallbacks_used += 1
    key = f"{provider}/{model}" if provider else model
    u.served_by[key] = u.served_by.get(key, 0) + 1
    p_in, p_out = PRICES.get(model, (0.0, 0.0))
    u.cost_usd = round(u.cost_usd + (prompt_toks * p_in + completion_toks * p_out) / 1_000_000, 6)


def record_search(cache_hit: bool) -> None:
    u = _current.get()
    if u is None:
        return
    if cache_hit:
        u.cache_hits += 1
    else:
        u.tavily_searches += 1
