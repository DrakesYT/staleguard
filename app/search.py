"""Live web search through Tavily, normalised into Evidence-shaped dicts.

`topic="news"` returns published dates, which the freshness score depends on.
A short in-memory cache avoids paying twice for identical queries within one session;
re-checks pass fresh=True to bypass it.
"""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

from . import mock, usage
from .config import settings

_CACHE_TTL = 600  # seconds
_cache: dict[tuple, tuple[float, list[dict]]] = {}
_client = None


class SearchError(RuntimeError):
    pass


def _tavily():
    global _client
    if _client is None:
        if not settings.tavily_api_key:
            raise SearchError("TAVILY_API_KEY is not set")
        from tavily import AsyncTavilyClient
        _client = AsyncTavilyClient(api_key=settings.tavily_api_key)
    return _client


def normalise_date(raw: str | None) -> str | None:
    """Tavily news dates come as RFC 2822 ('Mon, 10 Nov 2025 08:00:00 GMT') or ISO. Return YYYY-MM-DD."""
    if not raw:
        return None
    raw = raw.strip()
    try:
        return parsedate_to_datetime(raw).date().isoformat()
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


async def search(query: str, *, news: bool = False, days: int = 30, max_results: int = 5, fresh: bool = False) -> list[dict]:
    key = (query.lower().strip(), news, days, max_results)
    if not fresh and key in _cache and time.time() - _cache[key][0] < _CACHE_TTL:
        usage.record_search(cache_hit=True)
        return _cache[key][1]

    if settings.mock:
        results = mock.search(query, news=news)
    else:
        # include_published_date: general results carry dates too (news always does). The score needs them.
        kwargs: dict = {"query": query, "max_results": max_results, "search_depth": "basic",
                        "include_published_date": True}
        if news:
            # `days` is no longer in the Tavily API reference; start_date is the documented filter.
            kwargs.update(topic="news", start_date=(date.today() - timedelta(days=days)).isoformat())
        try:
            resp = await _tavily().search(**kwargs)
        except SearchError:
            raise
        except Exception as e:  # SDK raises various types
            raise SearchError(f"Tavily search failed: {e}") from e
        results = [
            {
                "url": r.get("url", ""),
                "title": r.get("title", ""),
                "snippet": (r.get("content") or "")[:600],
                "published": normalise_date(r.get("published_date")),
                "domain": _domain(r.get("url", "")),
            }
            for r in resp.get("results", [])
            if r.get("url")
        ]

    usage.record_search(cache_hit=False)
    _cache[key] = (time.time(), results)
    return results
