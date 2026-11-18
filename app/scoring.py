"""Deterministic, explainable freshness scoring.

The LLM only labels each piece of evidence (supports / contradicts / unrelated).
The score itself is computed here from evidence dates, agreement and contradiction, so it is
reproducible and every number can be explained to the user.

Each claim category has a half-life: how fast that kind of fact tends to go stale.
A pricing claim backed by a 90-day-old source is weaker than a leadership claim backed by the same source.
"""
from __future__ import annotations

from datetime import date

from .models import Evidence

HALF_LIFE_DAYS: dict[str, int] = {
    "pricing": 45,
    "api_version": 60,
    "product": 90,
    "funding": 120,
    "event": 120,
    "leadership": 180,
    "statistic": 180,
    "regulation": 240,
    "other": 365,
}
UNDATED_WEIGHT = 0.35   # evidence with no published date counts, but weakly


def recency(published: str | None, today: date, half_life: int) -> float:
    if not published:
        return UNDATED_WEIGHT
    try:
        d = date.fromisoformat(published[:10])
    except ValueError:
        return UNDATED_WEIGHT
    age = max(0, (today - d).days)
    return 0.5 ** (age / half_life)


def score(category: str, evidence: list[Evidence], today: date | None = None) -> tuple[str, int, list[str]]:
    """Return (verdict, freshness 0-100, human-readable reasons)."""
    today = today or date.today()
    hl = HALF_LIFE_DAYS.get(category, HALF_LIFE_DAYS["other"])
    sup = [e for e in evidence if e.stance == "supports"]
    con = [e for e in evidence if e.stance == "contradicts"]
    reasons: list[str] = [f"'{category}' facts go stale fast (half-life {hl} days)" if hl <= 90
                          else f"'{category}' facts change slowly (half-life {hl} days)"]

    if not sup and not con:
        reasons.append("No live source confirmed or contradicted this claim")
        return "unverified", 20, reasons

    w_sup = [recency(e.published, today, hl) for e in sup]
    w_con = [recency(e.published, today, hl) for e in con]
    best_sup = max(w_sup, default=0.0)
    total = sum(w_sup) + sum(w_con)
    con_share = sum(w_con) / total if total else 0.0
    sup_domains = len({e.domain for e in sup if e.domain})
    agreement = min(1.0, sup_domains / 3)

    freshness = 100 * (0.5 * best_sup + 0.25 * agreement + 0.25 * (1 - con_share))

    newest_sup = max((e.published for e in sup if e.published), default=None)
    newest_con = max((e.published for e in con if e.published), default=None)
    if sup:
        reasons.append(f"{len(sup)} source(s) on {sup_domains} domain(s) support it"
                       + (f"; newest {newest_sup}" if newest_sup else "; none dated"))
    if con:
        reasons.append(f"{len(con)} source(s) contradict it" + (f"; newest {newest_con}" if newest_con else ""))

    contradiction_is_newer = bool(con) and (newest_sup is None or (newest_con is not None and newest_con >= newest_sup))

    if con and (con_share >= 0.6 or (contradiction_is_newer and con_share >= 0.4)):
        verdict = "outdated"
        freshness = min(freshness, 25)
        reasons.append("Newer or stronger sources say something different")
    elif con and con_share >= 0.2:
        verdict = "disputed"
        freshness = min(freshness, 55)
        reasons.append("Sources disagree")
    elif best_sup < 0.4:
        verdict = "aging"
        reasons.append("Only older sources back this up; it may have changed")
    else:
        verdict = "current"

    return verdict, int(round(freshness)), reasons
