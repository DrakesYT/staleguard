"""Meeting-brief research agent (Tavily problem statement #5).

1. Research: several news searches over the last 30 days.
2. Write: the smart model drafts a one-page brief; every development must cite sources.
3. Each development becomes a Claim that the stale-answer engine verifies (statement #6).
"""
from __future__ import annotations

import uuid
from datetime import date

from .llm import chat_json
from .models import BriefContent, Claim, Source
from .search import search
from .claims import _valid_category

ANGLES = [
    "{e} latest news",
    "{e} funding OR acquisition OR earnings",
    "{e} launches OR announces new product",
    "{e} hires OR appoints OR steps down",
    "{e} partnership OR deal OR lawsuit",
]
MAX_SOURCES = 18

BRIEF_SYSTEM = """You write a one-page pre-meeting briefing. Today is {today}. The meeting is at {meeting}.
Subject: {entity}. Meeting purpose: {purpose}.

Use ONLY the numbered sources below. Focus on the last 30 days. Every development must cite source numbers.
Do not invent facts. If sources are thin, say so in watch_outs.

Return JSON:
{{"one_liner": "who/what they are + the single most important recent development (max 35 words)",
  "developments": [{{"text": "one factual sentence with a date if known", "category": "pricing|api_version|leadership|funding|regulation|product|statistic|event|other", "date": "YYYY-MM-DD or empty", "sources": [1, 2]}}],
  "talking_points": ["3-5 specific things to raise, tied to developments"],
  "open_questions": ["3-5 questions to ask in the meeting"],
  "watch_outs": ["0-3 risks, sensitivities or gaps in the research"]}}
Max 7 developments, most important first."""


async def research(entity: str) -> list[Source]:
    results: list[dict] = []
    for angle in ANGLES:
        results += await search(angle.format(e=entity), news=True, days=30, max_results=5)
    seen, unique = set(), []
    for r in results:
        if r["url"] not in seen:
            seen.add(r["url"])
            unique.append(r)
    unique.sort(key=lambda r: r.get("published") or "", reverse=True)
    return [Source(n=i + 1, **r) for i, r in enumerate(unique[:MAX_SOURCES])]


async def write_brief(entity: str, meeting_time: str, purpose: str, sources: list[Source]) -> tuple[BriefContent, list[Claim]]:
    listing = "\n\n".join(
        f"[{s.n}] {s.title} ({s.domain}, {s.published or 'undated'})\n{s.snippet}" for s in sources
    )
    data = await chat_json(
        [
            {"role": "system", "content": BRIEF_SYSTEM.format(
                today=date.today().isoformat(), meeting=meeting_time, entity=entity,
                purpose=purpose or "general introduction")},
            {"role": "user", "content": f"SOURCES:\n{listing}"},
        ],
        task="brief",
        smart=True,
        max_tokens=2000,
    )
    by_n = {s.n: s for s in sources}
    content = BriefContent(
        one_liner=str(data.get("one_liner", "")),
        talking_points=[str(x) for x in data.get("talking_points", [])][:5],
        open_questions=[str(x) for x in data.get("open_questions", [])][:5],
        watch_outs=[str(x) for x in data.get("watch_outs", [])][:3],
    )
    claims: list[Claim] = []
    for d in data.get("developments", [])[:7]:
        if not isinstance(d, dict) or not d.get("text"):
            continue
        cited = [by_n[n] for n in d.get("sources", []) if isinstance(n, int) and n in by_n]
        claims.append(Claim(
            id=uuid.uuid4().hex[:8],
            text=str(d["text"]),
            category=_valid_category(d.get("category", "event")),
            subject=entity,
            search_query=f"{entity} {str(d['text'])[:80]}",
            source_urls=[s.url for s in cited],
        ))
    return content, claims


def cited_evidence(claim: Claim, sources: list[Source]) -> list[dict]:
    """The brief's own cited sources, passed to the verifier alongside a fresh independent search."""
    by_url = {s.url: s for s in sources}
    return [by_url[u].model_dump(exclude={"n"}) for u in claim.source_urls if u in by_url]
