"""LLM access through the Bifrost gateway (OpenAI-compatible /v1/chat/completions).

Bifrost gives us: one API for every provider, automatic provider fallback (`fallbacks`),
and routing info in the response so we can show which provider actually served each call.
"""
from __future__ import annotations

import json
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar
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
    normal = settings.model_smart if smart else settings.model_fast
    outage = _outage.get()
    # Demo outage: ask for the unavailable model first and put the normal primary at the head of the
    # fallback chain, so Bifrost visibly fails over to it.
    model = settings.outage_model if outage else normal
    chain = ([normal] if outage else []) + settings.fallbacks

    if settings.mock:
        text = mock.chat(task, messages)
        usage.record_llm("mock", "mock-fallback" if outage else "mock-model", 300, 120, outage,
                         task=task, requested=model, ms=5)
        return text

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if settings.reasoning_effort:
        payload["reasoning_effort"] = settings.reasoning_effort
    fallbacks = list(dict.fromkeys(f for f in chain if f != model))   # de-dupe, keep order
    if fallbacks:
        payload["fallbacks"] = fallbacks

    headers = {"x-bf-vk": settings.bifrost_virtual_key} if settings.bifrost_virtual_key else {}
    t0 = time.perf_counter()
    try:
        r = await _http().post(f"{settings.bifrost_url}/v1/chat/completions", json=payload, headers=headers)
    except httpx.HTTPError as e:
        raise LLMError(f"Cannot reach Bifrost at {settings.bifrost_url}: {e}") from e
    if r.status_code != 200:
        raise LLMError(_explain_error(r))

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
        task=task,
        requested=model,
        ms=int((time.perf_counter() - t0) * 1000),
    )
    return text


def _explain_error(r: httpx.Response) -> str:
    """Turn Bifrost governance refusals into messages a user can act on."""
    try:
        kind = (r.json() or {}).get("type", "")
    except ValueError:
        kind = ""
    if r.status_code == 402 or kind == "budget_exceeded":
        return ("The daily budget on the Bifrost virtual key is used up, so Bifrost refused the call. "
                "Raise BIFROST_BUDGET_USD in .env and restart Bifrost, or wait for the daily reset.")
    if r.status_code == 401 or kind in ("virtual_key_required", "virtual_key_invalid"):
        return ("Bifrost refused the call: missing or unknown virtual key. Start Bifrost with "
                "scripts/start-bifrost.ps1 (it writes BIFROST_VIRTUAL_KEY to .env), then restart the app.")
    if r.status_code == 429 and kind in ("rate_limited", "token_limited", "request_limited"):
        return "The Bifrost virtual key's hourly rate limit was reached. Try again shortly."
    return f"Bifrost returned {r.status_code}: {r.text[:400]}"


async def budget_status() -> dict:
    """The app's virtual-key budget and rate limit, as Bifrost's governance API reports them."""
    if settings.mock:
        return {"available": False, "reason": "mock mode"}
    if not settings.bifrost_virtual_key:
        return {"available": False, "reason": "no virtual key configured"}
    try:
        r = await _http().get(f"{settings.bifrost_url}/api/governance/virtual-keys/{settings.bifrost_vk_id}",
                              headers={"X-Bifrost-Setup-Token": settings.bifrost_setup_token}, timeout=5)
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        return {"available": False, "reason": f"governance API: {e}"[:200]}
    vk = data.get("virtual_key", data)
    budget = (vk.get("budgets") or [{}])[0]
    rl = vk.get("rate_limit") or {}
    return {
        "available": True,
        "virtual_key": vk.get("id", settings.bifrost_vk_id),
        "name": vk.get("name", ""),
        "budget": {"used": float(budget.get("current_usage") or 0), "limit": float(budget.get("max_limit") or 0),
                   "reset": budget.get("reset_duration", ""), "last_reset": budget.get("last_reset", "")},
        "rate_limit": {
            "requests": [rl.get("request_current_usage", 0), rl.get("request_max_limit"), rl.get("request_reset_duration")],
            "tokens": [rl.get("token_current_usage", 0), rl.get("token_max_limit"), rl.get("token_reset_duration")],
        },
    }


_outage: ContextVar[bool] = ContextVar("simulate_outage", default=False)


@contextmanager
def simulate_outage(enabled: bool = True):
    """Within this block, every LLM call asks Bifrost for settings.outage_model first (demo of fallback).
    A ContextVar, so it only affects the current request, including the tasks it spawns."""
    token = _outage.set(enabled)
    try:
        yield
    finally:
        _outage.reset(token)


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
