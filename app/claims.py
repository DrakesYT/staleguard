"""Extract time-sensitive claims from an LLM answer."""
from __future__ import annotations

import uuid
from datetime import date

from .config import settings
from .llm import chat_json
from .models import Claim

CATEGORIES = "pricing, api_version, leadership, funding, regulation, product, statistic, event, other"

EXTRACT_SYSTEM = f"""You find claims in a text that can go out of date.
Today is {{today}}.

Extract ONLY factual claims whose truth can change over time, for example:
prices and plan limits; software/API/model versions and deprecations; who holds a role;
funding, valuations, acquisitions; laws, regulations and their status; product availability or features;
statistics and rankings; anything described as "latest", "current", "newest", "now".

Skip timeless facts, definitions, opinions, advice and instructions.

For each claim return:
- text: the claim as a self-contained sentence (resolve pronouns, include the subject)
- category: one of [{CATEGORIES}]
- subject: the product/company/person/law it is about
- value: the specific time-sensitive value asserted (e.g. "$20/month", "v3.2", "Jane Doe")
- search_query: a short web search query (max 10 words) that would reveal the CURRENT truth

Return at most {{max_claims}} claims, most important first, as JSON:
{{{{"claims": [{{{{"text": "...", "category": "...", "subject": "...", "value": "...", "search_query": "..."}}}}]}}}}
If there are none, return {{{{"claims": []}}}}."""


def _valid_category(c: str) -> str:
    c = (c or "other").strip().lower()
    return c if c in CATEGORIES.replace(" ", "").split(",") else "other"


async def extract_claims(text: str) -> list[Claim]:
    system = EXTRACT_SYSTEM.format(today=date.today().isoformat(), max_claims=settings.max_claims)
    data = await chat_json(
        [{"role": "system", "content": system}, {"role": "user", "content": text}],
        task="extract",
    )
    raw = data.get("claims", []) if isinstance(data, dict) else data
    claims: list[Claim] = []
    for item in raw[: settings.max_claims]:
        if not isinstance(item, dict) or not item.get("text"):
            continue
        claims.append(
            Claim(
                id=uuid.uuid4().hex[:8],
                text=str(item["text"]).strip(),
                category=_valid_category(item.get("category", "other")),
                subject=str(item.get("subject", "")).strip(),
                value=str(item.get("value", "")).strip(),
                search_query=str(item.get("search_query") or item["text"])[:200],
            )
        )
    return claims
