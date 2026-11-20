"""Offline stand-ins for Tavily and the LLM (STALEGUARD_MOCK=1).

Used for UI work without spending credits, for tests, and as a demo backup if the network dies.
Output is deterministic (hash-based) so the same input always gives the same verdicts.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, timedelta

KEYWORDS = {
    "pricing": ["price", "$", "cost", "per month", "/month", "plan", "tier"],
    "api_version": ["version", "v1", "v2", "v3", "v4", "api", "sdk", "release", "deprecated"],
    "leadership": ["ceo", "cto", "founder", "president", "head of", "appointed", "chair"],
    "funding": ["raised", "funding", "valuation", "series", "acquired", "ipo"],
    "regulation": ["law", "act", "regulation", "ban", "compliance", "gdpr"],
    "statistic": ["%", "million users", "billion", "market share", "ranked"],
    "product": ["latest", "launched", "new model", "available", "feature", "newest", "current"],
}


def _h(s: str) -> int:
    return int(hashlib.md5(s.encode()).hexdigest(), 16)


def _category(sentence: str) -> str:
    low = sentence.lower()
    for cat, words in KEYWORDS.items():
        if any(w in low for w in words):
            return cat
    return "other"


def search(query: str, news: bool = False) -> list[dict]:
    today = date.today()
    slug = re.sub(r"[^a-z0-9]+", "-", query.lower())[:40].strip("-")
    base = _h(query)
    domains = ["techcrunch.com", "reuters.com", "theverge.com", "docs.example.com", "bloomberg.com", "wired.com"]
    out = []
    for i in range(3):
        age = [4, 40, 260][i] + (base >> i) % 10
        out.append({
            "url": f"https://{domains[(base + i) % len(domains)]}/{slug}-{i}{'-news' if news else ''}",
            "title": f"{'News: ' if news else ''}{query.title()} - update {i + 1}",
            "snippet": f"Coverage of {query}. Mock source {i + 1} for offline mode.",
            "published": (today - timedelta(days=age)).isoformat() if (i < 2 or news) else None,
            "domain": domains[(base + i) % len(domains)],
        })
    return out


def _user(messages) -> str:
    return next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")


def chat(task: str, messages) -> str:
    text = _user(messages)
    if task == "extract":
        sentences = re.split(r"(?<=[.!?])\s+", text)
        picked = [s.strip() for s in sentences
                  if re.search(r"\d|latest|current|ceo|price|version|newest", s, re.I)][:6]
        return json.dumps({"claims": [
            {"text": s, "category": _category(s), "subject": s.split()[0] if s.split() else "",
             "value": (re.findall(r"\$?\d[\d.,]*%?", s) or [""])[0], "search_query": s[:80], "quote": s}
            for s in picked
        ]})
    if task == "stance":
        n = len(re.findall(r"^\[\d+\]", text, re.M))
        claim = text.split("\n", 1)[0]
        mode = _h(claim) % 4   # 0,1 current-ish; 2 disputed; 3 outdated
        stances = []
        for i in range(n):
            if mode == 3:
                st = "contradicts" if i == 0 else ("supports" if i == n - 1 else "unrelated")
            elif mode == 2:
                st = "contradicts" if i == 1 else "supports"
            else:
                st = "supports" if i < 2 else "unrelated"
            stances.append({"i": i, "stance": st, "note": f"mock {st}"})
        return json.dumps({"stances": stances, "current_value": "a newer value (mock)" if mode >= 2 else ""})
    if task == "brief":
        nums = re.findall(r"^\[(\d+)\] (.+?) \(", text, re.M)[:5]
        return json.dumps({
            "one_liner": "Mock company in offline mode; most important recent development is a product launch.",
            "developments": [
                {"text": f"{title} was reported this month.", "category": ["product", "funding", "leadership", "event", "pricing"][i % 5],
                 "date": "", "sources": [int(n)]}
                for i, (n, title) in enumerate(nums)
            ],
            "talking_points": ["Ask how the recent launch is landing with customers", "Reference the funding news",
                               "Explore partnership fit"],
            "open_questions": ["What are your priorities for next quarter?", "Who owns the budget for this?",
                               "What would success look like in 90 days?"],
            "watch_outs": ["Mock mode: no real research was done"],
        })
    if task == "refresh":
        answer = text.split("ANSWER:\n", 1)[-1]
        return answer + "\n\n[updated: mock mode - corrections would be applied here]"
    return "{}"
