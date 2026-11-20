"""Deterministic, explainable freshness scoring.

The LLM only labels each piece of evidence (supports / contradicts / unrelated).
The score itself is computed here from evidence dates, source authority, agreement and contradiction,
so it is reproducible and every number can be explained to the user.

Each claim category has a half-life: how fast that kind of fact tends to go stale.
A pricing claim backed by a 90-day-old source is weaker than a leadership claim backed by the same source.

Each source also has an authority tier, decided from its URL alone (no LLM):
official/government > docs & changelogs > reference & major news > default > user-generated.
Reference pages and docs are "living documents": search engines report their creation date, not their
last edit (Tavily dates Wikipedia's Python page 2009), so their dates are ignored for recency.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlparse

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
LIVING_WEIGHT = 0.6     # maintained reference/docs page whose real update date we can't know


@dataclass(frozen=True)
class Authority:
    tier: str        # official | docs | reference | news | default | user
    weight: float
    living: bool     # date is the page's creation date, not its last update -> ignore it
    label: str


TIERS = {
    "official": 1.5,
    "docs": 1.4,
    "reference": 1.2,
    "news": 1.2,
    "default": 1.0,
    "user": 0.6,
}
TIER_TEXT = {
    "official": "official or government",
    "docs": "documentation / changelog",
    "reference": "reference",
    "news": "major news",
    "user": "user-generated",
}

GOV = re.compile(r"(\.gov|\.mil|\.int|\.gov\.[a-z]{2}|\.gob\.[a-z]{2}|\.gc\.ca|\.gouv\.fr|europa\.eu|\.go\.jp)$")
REFERENCE = {"wikipedia.org", "britannica.com", "endoflife.date", "investopedia.com"}
NEWS = {
    "reuters.com", "apnews.com", "bloomberg.com", "ft.com", "wsj.com", "nytimes.com", "bbc.com", "bbc.co.uk",
    "cnbc.com", "theguardian.com", "washingtonpost.com", "economist.com", "techcrunch.com", "theverge.com",
    "arstechnica.com", "wired.com", "axios.com", "fortune.com", "forbes.com", "npr.org", "politico.com",
    "theinformation.com", "semafor.com",
}
USER = {
    "youtube.com", "x.com", "twitter.com", "facebook.com", "instagram.com", "tiktok.com", "reddit.com",
    "quora.com", "medium.com", "linkedin.com", "pinterest.com", "threads.net",
}
DOCS_HOST = re.compile(r"^(docs|developer|developers|dev|devblogs|learn|support|help|api|platform)\.")
DOCS_PATH = re.compile(r"/(docs?|documentation|changelog|release-notes|releases?|whatsnew|api-reference|reference)(/|$|-)", re.I)


def _registrable(host: str) -> str:
    """'docs.python.org' -> 'python.org', 'en.wikipedia.org' -> 'wikipedia.org' (good enough for our lists)."""
    parts = host.split(".")
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in ("co", "com", "org", "gov", "ac", "net"):
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def authority(url: str, domain: str = "", subject: str = "") -> Authority:
    host = (urlparse(url).netloc or domain).lower().removeprefix("www.")
    path = urlparse(url).path
    reg = _registrable(host) if host else ""
    name = reg.split(".")[0] if reg else ""

    if GOV.search(host):
        return Authority("official", TIERS["official"], False, host)
    # The subject's own site (stripe.com for Stripe, python.org for Python), incl. its docs/newsroom.
    subject_tokens = {_norm(t) for t in re.split(r"[\s/,()]+", subject)} | {_norm(subject)} if subject else set()
    if name and len(name) >= 3 and _norm(name) in subject_tokens:
        return Authority("official", TIERS["official"], bool(DOCS_PATH.search(path) or DOCS_HOST.match(host)), reg)
    if DOCS_HOST.match(host) or DOCS_PATH.search(path):
        return Authority("docs", TIERS["docs"], True, host)
    if reg in REFERENCE:
        return Authority("reference", TIERS["reference"], True, reg)
    if reg in NEWS:
        return Authority("news", TIERS["news"], False, reg)
    if reg in USER:
        return Authority("user", TIERS["user"], False, reg)
    return Authority("default", TIERS["default"], False, reg or host)


def recency(published: str | None, today: date, half_life: int) -> float:
    if not published:
        return UNDATED_WEIGHT
    try:
        d = date.fromisoformat(published[:10])
    except ValueError:
        return UNDATED_WEIGHT
    age = max(0, (today - d).days)
    return 0.5 ** (age / half_life)


def _weigh(e: Evidence, today: date, hl: int, subject: str) -> tuple[float, str | None, Authority]:
    """(weight, trusted date or None, authority) for one piece of evidence."""
    a = authority(e.url, e.domain, subject)
    if a.living:
        return LIVING_WEIGHT * a.weight, None, a
    return recency(e.published, today, hl) * a.weight, e.published, a


def score(category: str, evidence: list[Evidence], today: date | None = None,
          subject: str = "") -> tuple[str, int, list[str]]:
    """Return (verdict, freshness 0-100, human-readable reasons)."""
    today = today or date.today()
    hl = HALF_LIFE_DAYS.get(category, HALF_LIFE_DAYS["other"])
    sup = [_weigh(e, today, hl, subject) for e in evidence if e.stance == "supports"]
    con = [_weigh(e, today, hl, subject) for e in evidence if e.stance == "contradicts"]
    reasons: list[str] = [f"'{category}' facts go stale fast (half-life {hl} days)" if hl <= 90
                          else f"'{category}' facts change slowly (half-life {hl} days)"]

    if not sup and not con:
        reasons.append("No live source confirmed or contradicted this claim")
        return "unverified", 20, reasons

    w_sup = [w for w, _, _ in sup]
    w_con = [w for w, _, _ in con]
    best_sup = min(1.0, max(w_sup, default=0.0))
    total = sum(w_sup) + sum(w_con)
    con_share = sum(w_con) / total if total else 0.0
    sup_domains = len({a.label for _, _, a in sup})
    agreement = min(1.0, sup_domains / 3)

    freshness = 100 * (0.5 * best_sup + 0.25 * agreement + 0.25 * (1 - con_share))

    newest_sup = max((d for _, d, _ in sup if d), default=None)
    newest_con = max((d for _, d, _ in con if d), default=None)
    if sup:
        reasons.append(f"{len(sup)} source(s) on {sup_domains} domain(s) support it"
                       + (f"; newest {newest_sup}" if newest_sup else "; none with a trusted date"))
    if con:
        reasons.append(f"{len(con)} source(s) contradict it" + (f"; newest {newest_con}" if newest_con else ""))
    reasons += _authority_reasons(sup, con)

    # A contradiction counts as newer when it is dated after the newest support, or when it comes from
    # a maintained page (living document) and no support is recent.
    con_living = any(a.living for _, _, a in con)
    sup_recent = any(d and (today - date.fromisoformat(d[:10])).days <= hl for _, d, _ in sup)
    contradiction_is_newer = bool(con) and (
        newest_sup is None
        or (newest_con is not None and newest_con >= newest_sup)
        or (con_living and not sup_recent)
    )

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


def _authority_reasons(sup, con) -> list[str]:
    """One line on which sources counted extra or less, and which dates were ignored."""
    out = []
    strong = sorted({f"{a.label}" for _, _, a in sup + con if a.tier in ("official", "docs")})
    weak = sorted({a.label for _, _, a in sup + con if a.tier == "user"})
    living = sorted({a.label for _, _, a in sup + con if a.living})
    if strong:
        out.append(f"Official/docs sources weigh more: {', '.join(strong[:4])}")
    if weak:
        out.append(f"User-generated sources weigh less: {', '.join(weak[:4])}")
    if living:
        out.append(f"Dates ignored for maintained pages (search engines report their creation date): "
                   f"{', '.join(living[:4])}")
    return out
