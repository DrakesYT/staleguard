"""Re-verify one claim against the live web and score its freshness."""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from .llm import chat_json
from .models import Claim, ClaimResult, Evidence
from .scoring import score
from .search import dedupe, search

log = logging.getLogger("staleguard")

# Categories where recent news coverage matters most; we add a news-topic search for these.
NEWSY = {"leadership", "funding", "regulation", "event", "product", "pricing"}
MAX_EVIDENCE = 7

STANCE_SYSTEM = """You check whether web sources confirm a claim TODAY. Today is {today}.

For each numbered source decide:
- "supports": the source states the same value/fact as the claim
- "contradicts": the source gives a different/newer value, or says it changed, ended or was replaced
- "unrelated": the source does not address the specific value in the claim

Judge only from the source text. Prefer the source's stated date over your own knowledge.
Also give current_value: the up-to-date value according to the sources if it differs from the claim, else "".

Reply as JSON:
{{"stances": [{{"i": 0, "stance": "supports|contradicts|unrelated", "note": "max 15 words"}}],
  "current_value": ""}}"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def gather_evidence(claim: Claim, *, fresh: bool = False, extra: list[dict] | None = None) -> list[dict]:
    q = claim.search_query or claim.text
    found = list(extra or [])
    found += await search(q, max_results=5, fresh=fresh)
    if claim.category in NEWSY:
        found += await search(q, news=True, days=180, max_results=5, fresh=fresh)
    # Dated sources first (newest first), undated after: the score depends on dates.
    found = dedupe(found)
    found.sort(key=lambda r: r.get("published") or "", reverse=True)
    return found[:MAX_EVIDENCE]


async def verify_claim(claim: Claim, *, fresh: bool = False, extra: list[dict] | None = None) -> ClaimResult:
    """Check one claim. A failure here marks only this claim unverified (with `error` set), so one bad
    search or model reply doesn't sink the whole report. pipeline raises if every claim failed."""
    try:
        return await _verify_claim(claim, fresh=fresh, extra=extra)
    except Exception as e:  # noqa: BLE001 - reported on the claim, and re-raised by pipeline if all fail
        log.warning("claim check failed (%s): %s", claim.text[:60], e)
        return ClaimResult(claim=claim, verdict="unverified", freshness=20, checked_at=_now(),
                           reasons=["The check failed, so this claim was not verified"],
                           error=f"{type(e).__name__}: {e}"[:300])


async def _verify_claim(claim: Claim, *, fresh: bool = False, extra: list[dict] | None = None) -> ClaimResult:
    raw = await gather_evidence(claim, fresh=fresh, extra=extra)
    if not raw:
        verdict, fresh_score, reasons = score(claim.category, [])
        return ClaimResult(claim=claim, verdict=verdict, freshness=fresh_score,
                           reasons=reasons, checked_at=_now())

    listing = "\n\n".join(
        f"[{i}] {r['title']} ({r['domain']}, published {r.get('published') or 'unknown'})\n{r['snippet']}"
        for i, r in enumerate(raw)
    )
    data = await chat_json(
        [
            {"role": "system", "content": STANCE_SYSTEM.format(today=date.today().isoformat())},
            {"role": "user", "content": f"CLAIM: {claim.text}\nVALUE: {claim.value or '-'}\n\nSOURCES:\n{listing}"},
        ],
        task="stance",
        max_tokens=800,
    )
    stances = {}
    for s in (data.get("stances", []) if isinstance(data, dict) else []):
        try:
            stances[int(s.get("i"))] = s
        except (TypeError, ValueError):
            continue

    evidence: list[Evidence] = []
    for i, r in enumerate(raw):
        s = stances.get(i, {})
        stance = s.get("stance") if s.get("stance") in ("supports", "contradicts", "unrelated") else "unrelated"
        evidence.append(Evidence(**r, stance=stance, note=str(s.get("note", ""))[:200]))

    verdict, fresh_score, reasons = score(claim.category, evidence)
    current_value = str(data.get("current_value", "") if isinstance(data, dict) else "").strip()
    if verdict in ("current", "unverified"):
        current_value = ""
    # Relevant evidence first in the UI.
    order = {"contradicts": 0, "supports": 1, "unrelated": 2}
    evidence.sort(key=lambda e: order[e.stance])
    return ClaimResult(claim=claim, verdict=verdict, freshness=fresh_score, reasons=reasons,
                       current_value=current_value, evidence=evidence, checked_at=_now())
