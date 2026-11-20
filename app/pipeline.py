"""End-to-end flows: verify an answer, build a brief, re-check a brief."""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import date, datetime, timezone

from . import llm, store, usage
from .brief import cited_evidence, research, write_brief
from .claims import extract_claims
from .config import settings
from .llm import chat
from .models import Brief, CheckEvent, ClaimResult, Usage, VerifyReport
from .verify import verify_claim

VERDICTS = ["current", "aging", "disputed", "outdated", "unverified"]


class CheckFailed(RuntimeError):
    """Every claim check in a run failed (upstream outage)."""

REFRESH_SYSTEM = """Rewrite the answer so it is up to date. Today is {today}.
Apply ONLY the corrections listed. Keep everything else, including tone and structure.
After each corrected statement add a marker like [updated: <source domain>].
If a claim is only disputed, keep it but add "(sources disagree - verify)".
Return only the rewritten answer."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def _verify_all(jobs) -> list[ClaimResult]:
    sem = asyncio.Semaphore(settings.concurrency)

    async def run(coro):
        async with sem:
            return await coro

    results = list(await asyncio.gather(*(run(j) for j in jobs)))
    _raise_if_all_failed(results)
    return results


def _raise_if_all_failed(results: list[ClaimResult]) -> None:
    if results and all(r.error for r in results):
        # Every check failed: almost certainly an outage (Bifrost/Tavily down), not bad claims.
        raise CheckFailed(f"All {len(results)} claim checks failed. First error: {results[0].error}")


def _summary(results: list[ClaimResult]) -> tuple[int, dict[str, int]]:
    counts = {v: 0 for v in VERDICTS}
    for r in results:
        counts[r.verdict] += 1
    overall = round(sum(r.freshness for r in results) / len(results)) if results else 100
    return overall, counts


async def _refresh(text: str, results: list[ClaimResult]) -> str:
    fixes = []
    for r in results:
        if r.verdict not in ("outdated", "disputed"):
            continue
        src = next((e.domain for e in r.evidence if e.stance == "contradicts"), "")
        fixes.append(f"- [{r.verdict}] \"{r.claim.text}\" -> current: {r.current_value or 'unclear'} (source: {src})")
    if not fixes:
        return ""
    return await chat(
        [
            {"role": "system", "content": REFRESH_SYSTEM.format(today=date.today().isoformat())},
            {"role": "user", "content": f"CORRECTIONS:\n{chr(10).join(fixes)}\n\nANSWER:\n{text}"},
        ],
        task="refresh",
        smart=True,
        max_tokens=2000,
    )


async def verify_answer_events(text: str, as_of: str | None = None,
                               simulate_outage: bool = False) -> AsyncIterator[tuple[str, dict]]:
    """Verify an answer, yielding progress events as they happen (drives the SSE endpoint):

    claims   {"claims": [...]}           extracted claims, with their location in the text
    result   ClaimResult                 one per claim, in the order checks FINISH
    refresh  {}                          the refreshed answer is being written
    done     VerifyReport                final report (also saved)
    """
    with usage.track() as u, llm.simulate_outage(simulate_outage):
        claims = await extract_claims(text)
        yield "claims", {"claims": [c.model_dump(mode="json") for c in claims]}

        sem = asyncio.Semaphore(settings.concurrency)

        async def run(c):
            async with sem:
                return await verify_claim(c)

        tasks = [asyncio.create_task(run(c)) for c in claims]   # tasks inherit usage + outage context
        by_id: dict[str, ClaimResult] = {}
        try:
            for fut in asyncio.as_completed(tasks):
                r = await fut
                by_id[r.claim.id] = r
                yield "result", r.model_dump(mode="json")
        finally:
            for t in tasks:   # client went away mid-stream: stop paying for searches
                t.cancel()
        results = [by_id[c.id] for c in claims]
        _raise_if_all_failed(results)

        if any(r.verdict in ("outdated", "disputed") for r in results):
            yield "refresh", {}
        refreshed = await _refresh(text, results)

    overall, counts = _summary(results)
    report = VerifyReport(
        id=uuid.uuid4().hex[:10], created_at=_now(), input_text=text, as_of=as_of,
        results=results, overall=overall, summary=counts, refreshed_answer=refreshed, usage=u,
        simulated_outage=simulate_outage,
    )
    store.save("report", report)
    yield "done", report.model_dump(mode="json")


async def verify_answer(text: str, as_of: str | None = None, simulate_outage: bool = False) -> VerifyReport:
    report = None
    async for event, data in verify_answer_events(text, as_of, simulate_outage):
        if event == "done":
            report = VerifyReport.model_validate(data)
    assert report is not None
    return report


async def create_brief(entity: str, meeting_time: str, purpose: str = "",
                       simulate_outage: bool = False) -> Brief:
    with usage.track() as u, llm.simulate_outage(simulate_outage):
        sources = await research(entity)
        content, claims = await write_brief(entity, meeting_time, purpose, sources)
        results = await _verify_all(verify_claim(c, extra=cited_evidence(c, sources)) for c in claims)
    brief = Brief(
        id=uuid.uuid4().hex[:10], entity=entity, purpose=purpose, meeting_time=meeting_time,
        created_at=_now(), sources=sources, content=content, developments=results,
        checks=[CheckEvent(at=_now(), trigger="created")], usage=u,
    )
    store.save("brief", brief)
    return brief


def _add_usage(total: Usage, extra: Usage) -> Usage:
    merged = total.model_copy(deep=True)
    for f in ("llm_calls", "prompt_tokens", "completion_tokens", "fallbacks_used", "tavily_searches", "cache_hits"):
        setattr(merged, f, getattr(merged, f) + getattr(extra, f))
    merged.cost_usd = round(merged.cost_usd + extra.cost_usd, 6)
    for k, v in extra.served_by.items():
        merged.served_by[k] = merged.served_by.get(k, 0) + v
    merged.calls = (merged.calls + extra.calls)[-usage.MAX_CALL_LOG:]
    return merged


async def recheck_brief(brief: Brief, trigger: str = "manual") -> Brief:
    """Re-verify every development with fresh searches and record what changed."""
    with usage.track() as u:
        new = await _verify_all(
            verify_claim(r.claim, fresh=True, extra=cited_evidence(r.claim, brief.sources))
            for r in brief.developments
        )
    changes = []
    for old, cur in zip(brief.developments, new):
        if old.verdict != cur.verdict:
            changes.append(f"\"{cur.claim.text[:90]}\": {old.verdict} -> {cur.verdict}"
                           + (f" (now: {cur.current_value})" if cur.current_value else ""))
        elif cur.current_value and cur.current_value != old.current_value:
            changes.append(f"\"{cur.claim.text[:90]}\": current value now {cur.current_value}")
    brief.developments = new
    brief.checks.append(CheckEvent(at=_now(), trigger=trigger, changes=changes))
    brief.usage = _add_usage(brief.usage, u)
    if trigger == "pre_meeting":
        brief.pre_meeting_checked = True
    store.save("brief", brief)
    return brief


async def due_for_pre_meeting(now: datetime | None = None) -> list[Brief]:
    now = now or datetime.now(timezone.utc)
    due = []
    for b in store.list_items("brief", Brief, limit=200):
        if b.pre_meeting_checked:
            continue
        try:
            mt = datetime.fromisoformat(b.meeting_time.replace("Z", "+00:00"))
        except ValueError:
            continue
        if mt.tzinfo is None:
            mt = mt.replace(tzinfo=timezone.utc)
        minutes = (mt - now).total_seconds() / 60
        if 0 <= minutes <= settings.recheck_window_min:
            due.append(b)
    return due
