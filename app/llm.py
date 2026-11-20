"""LLM access through the Bifrost gateway (OpenAI-compatible /v1/chat/completions).

Bifrost gives us: one API for every provider, automatic provider fallback (`fallbacks`),
and routing info in the response so we can show which provider actually served each call.
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

from . import mock, usage
from .config import settings

_client: httpx.AsyncClient | None = None


class LLMError(RuntimeError):
    pass


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=5.0))
    return _client


async def chat(
    messages: list[dict[str, str]],
    *,
    task: str,
    smart: bool = False,
    temperature: float = 0.1,
    max_tokens: int = 1500,
) -> str:
    """Send a chat request via Bifrost and return the assistant text.

    `task` labels the call (extract / stance / brief / refresh) for mock mode and logs.
    """
    if settings.mock:
        text = mock.chat(task, messages)
        usage.record_llm("mock", "mock-model", 300, 120, False)
        return text

    model = settings.model_smart if smart else settings.model_fast
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if settings.reasoning_effort:
        payload["reasoning_effort"] = settings.reasoning_effort
    fallbacks = [f for f in settings.fallbacks if f != model]
    if fallbacks:
        payload["fallbacks"] = fallbacks

    try:
        r = await _http().post(f"{settings.bifrost_url}/v1/chat/completions", json=payload)
    except httpx.HTTPError as e:
        raise LLMError(f"Cannot reach Bifrost at {settings.bifrost_url}: {e}") from e
    if r.status_code != 200:
        raise LLMError(f"Bifrost returned {r.status_code}: {r.text[:400]}")

    data = r.json()
    try:
        text = content_text(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError(f"Unexpected Bifrost response: {str(data)[:400]}") from e

    u = data.get("usage") or {}
    routing = (data.get("extra_fields") or {}).get("routing_info") or {}
    served_model = routing.get("model") or model.split("/", 1)[-1]
    served_provider = routing.get("provider") or (model.split("/", 1)[0] if "/" in model else "")
    usage.record_llm(
        served_provider,
        served_model,
        int(u.get("prompt_tokens") or 0),
        int(u.get("completion_tokens") or 0),
        bool(routing.get("is_fallback")),
    )
    return text


def content_text(content: Any) -> str:
    """Message content as plain text. Some providers (Gemini via Bifrost) sometimes return a list of
    content parts instead of a string; keep the text parts and drop reasoning/thinking parts."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for part in content:
            if isinstance(part, str):
                out.append(part)
            elif isinstance(part, dict) and part.get("type", "text") in ("text", "output_text"):
                out.append(str(part.get("text") or ""))
        return "".join(out)
    raise TypeError(f"unsupported content type {type(content).__name__}")


def parse_json(text: str) -> Any:
    """Extract the first JSON object/array from model output (tolerates ``` fences and chatter)."""
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1)
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        raise ValueError("no JSON found in model output")
    obj, _ = json.JSONDecoder().raw_decode(text[min(starts):])
    return obj


async def chat_json(messages: list[dict[str, str]], *, task: str, smart: bool = False, max_tokens: int = 1500) -> Any:
    """chat() + JSON parsing, with one repair retry if the model returns invalid JSON."""
    text = await chat(messages, task=task, smart=smart, max_tokens=max_tokens)
    try:
        return parse_json(text)
    except ValueError:
        repair = messages + [
            {"role": "assistant", "content": text},
            {"role": "user", "content": "That was not valid JSON. Reply with ONLY the JSON, no prose."},
        ]
        return parse_json(await chat(repair, task=task, smart=smart, max_tokens=max_tokens))
