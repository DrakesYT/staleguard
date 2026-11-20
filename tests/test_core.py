import os
from datetime import date, timedelta

os.environ["STALEGUARD_MOCK"] = "1"
os.environ["DB_PATH"] = os.path.join(os.path.dirname(__file__), "_test.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.llm import parse_json  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Evidence  # noqa: E402
from app.scoring import score  # noqa: E402
from app.search import normalise_date  # noqa: E402

TODAY = date(2026, 11, 18)


def ev(stance, days_ago, domain="a.com"):
    pub = (TODAY - timedelta(days=days_ago)).isoformat() if days_ago is not None else None
    return Evidence(url=f"https://{domain}/{stance}{days_ago}", stance=stance, published=pub, domain=domain)


def test_recent_agreeing_sources_are_current():
    v, f, _ = score("pricing", [ev("supports", 3, "a.com"), ev("supports", 10, "b.com"), ev("supports", 5, "c.com")], TODAY)
    assert v == "current" and f >= 80


def test_newer_contradiction_is_outdated():
    v, f, _ = score("pricing", [ev("supports", 200, "a.com"), ev("contradicts", 5, "b.com")], TODAY)
    assert v == "outdated" and f <= 25


def test_old_support_only_is_aging():
    v, _, _ = score("pricing", [ev("supports", 300, "a.com")], TODAY)
    assert v == "aging"


def test_same_age_matters_less_for_slow_categories():
    _, fast, _ = score("pricing", [ev("supports", 120)], TODAY)
    _, slow, _ = score("regulation", [ev("supports", 120)], TODAY)
    assert slow > fast


def test_authority_tiers_from_url():
    from app.scoring import authority
    assert authority("https://www.congress.gov/x").tier == "official"
    assert authority("https://digital-strategy.ec.europa.eu/en/policies/ai-act").tier == "official"
    assert authority("https://stripe.com/newsroom/x", subject="Stripe").tier == "official"
    assert authority("https://news.microsoft.com/build-2026", subject="Microsoft").tier == "official"
    assert authority("https://docs.python.org/3/whatsnew/3.15.html").tier == "docs"
    assert authority("https://nodejs.org/en/blog/release/v26.13.0").tier == "docs"
    assert authority("https://en.wikipedia.org/wiki/Python").tier == "reference"
    assert authority("https://www.reuters.com/x").tier == "news"
    assert authority("https://www.youtube.com/watch?v=1").tier == "user"
    assert authority("https://x.com/someone/status/1", subject="X").tier == "user"   # 'x' too short to match
    assert authority("https://randomblog.io/post").tier == "default"


def test_official_contradiction_beats_user_generated_support():
    sup = Evidence(url="https://www.youtube.com/watch?v=1", domain="youtube.com", stance="supports",
                   published=(TODAY - timedelta(days=10)).isoformat())
    con = Evidence(url="https://docs.example.com/changelog", domain="docs.example.com", stance="contradicts",
                   published=(TODAY - timedelta(days=10)).isoformat())
    v, _, reasons = score("api_version", [sup, con], TODAY)
    assert v == "outdated"
    assert any("Official/docs sources weigh more" in r for r in reasons)
    assert any("User-generated sources weigh less" in r for r in reasons)


def test_living_document_dates_are_ignored():
    # Tavily dates Wikipedia pages by creation (2009). A maintained page contradicting the claim must not
    # lose to a 2025 blog just because of that bogus date.
    wiki = Evidence(url="https://en.wikipedia.org/wiki/History_of_Python", domain="en.wikipedia.org",
                    stance="contradicts", published="2009-02-01")
    blog = Evidence(url="https://blog.example.com/python", domain="blog.example.com",
                    stance="supports", published=(TODAY - timedelta(days=400)).isoformat())
    v, _, reasons = score("api_version", [wiki, blog], TODAY)
    assert v == "outdated"
    assert any("Dates ignored for maintained pages" in r for r in reasons)


def test_living_document_support_keeps_claim_current():
    wiki = Evidence(url="https://en.wikipedia.org/wiki/Microsoft", domain="en.wikipedia.org",
                    stance="supports", published="2004-01-01")
    news = Evidence(url="https://www.reuters.com/x", domain="reuters.com", stance="supports",
                    published=(TODAY - timedelta(days=5)).isoformat())
    v, _, _ = score("leadership", [wiki, news], TODAY)
    assert v == "current"


def test_no_relevant_evidence_is_unverified():
    v, _, _ = score("other", [ev("unrelated", 1)], TODAY)
    assert v == "unverified"


def test_parse_json_tolerates_fences_and_chatter():
    assert parse_json('Sure!\n```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('here: {"claims": []} done') == {"claims": []}


def test_content_text_handles_part_lists():
    from app.llm import content_text
    assert content_text("plain") == "plain"
    assert content_text(None) == ""
    parts = [{"type": "reasoning", "text": "thinking..."}, {"type": "text", "text": '{"a": '}, {"type": "text", "text": "1}"}]
    assert parse_json(content_text(parts)) == {"a": 1}


def test_source_numbers_accepts_loose_formats():
    from app.brief import _source_numbers
    assert _source_numbers([1, "2", "[3]"]) == [1, 2, 3]
    assert _source_numbers("4, 5") == [4, 5]
    assert _source_numbers(None) == []


def test_one_failed_claim_does_not_sink_the_run(monkeypatch):
    import asyncio

    from app import verify
    from app.models import Claim

    async def boom(*a, **k):
        raise RuntimeError("search exploded")

    monkeypatch.setattr(verify, "gather_evidence", boom)
    r = asyncio.run(verify.verify_claim(Claim(id="x", text="X costs $5", category="pricing")))
    assert r.verdict == "unverified" and "search exploded" in r.error


def test_google_redirects_and_duplicate_titles():
    from app.search import _domain, dedupe
    assert _domain("https://www.google.com/url?opi=1&q=abc") == "news.google.com"
    assert _domain("https://www.reuters.com/x") == "reuters.com"
    items = [
        {"url": "https://a.com/1", "title": "Stripe Wants to Become the Financial OS for AI"},
        {"url": "https://www.google.com/url?q=zz", "title": "Stripe Wants to Become the Financial OS for AI - Substack"},
        {"url": "https://a.com/1", "title": "other"},
    ]
    assert [i["url"] for i in dedupe(items)] == ["https://a.com/1"]


def test_brief_sources_must_name_the_entity():
    from app.brief import mentions
    assert mentions("Stripe", {"title": "HSBC UK and Stripe launch Tap to Pay", "snippet": ""})
    assert not mentions("Stripe", {"title": "Stars and Stripes: new director appointed", "snippet": ""})


def test_locate_claim_in_text():
    from app.claims import locate
    text = "Hi there. Twitter's CEO is  Parag Agrawal, says the bot. Python 3.11 is newest!"
    assert text[slice(*locate(text, "Twitter's CEO is  Parag Agrawal"))] == "Twitter's CEO is  Parag Agrawal"
    # re-spaced / re-cased quote still found
    assert text[slice(*locate(text, "twitter's ceo is parag agrawal."))] == "Twitter's CEO is  Parag Agrawal"
    # paraphrased quote: fall back to the sentence containing the value
    assert text[slice(*locate(text, "The newest Python is 3.11", "Python 3.11"))] == "Python 3.11 is newest!"
    assert locate(text, "nothing like this", "") is None


def _sse_events(body: str) -> list[tuple[str, dict]]:
    import json
    out = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def test_stream_emits_claims_results_done():
    text = "The ChatGPT Plus plan costs $20 per month. The latest Python version is 3.12. Paris is in France."
    with TestClient(app) as c:
        r = c.post("/api/verify/stream", json={"text": text})
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        events = _sse_events(r.text)
    names = [e for e, _ in events]
    assert names[0] == "claims" and names[-1] == "done"
    claims = events[0][1]["claims"]
    assert claims and all(cl["span"] for cl in claims)
    assert names.count("result") == len(claims)
    done = events[-1][1]
    assert {r["claim"]["id"] for r in done["results"]} == {cl["id"] for cl in claims}
    assert done["usage"]["calls"] and done["usage"]["calls"][0]["task"] == "extract"


def test_simulated_outage_shows_fallback():
    with TestClient(app) as c:
        r = c.post("/api/verify", json={"text": "The latest Python version is 3.12 and it costs $0.", "simulate_outage": True})
    rep = r.json()
    assert rep["simulated_outage"] is True
    assert rep["usage"]["fallbacks_used"] == rep["usage"]["llm_calls"] > 0
    assert all(call["fallback"] for call in rep["usage"]["calls"])


def test_normalise_date():
    assert normalise_date("Mon, 10 Nov 2025 08:00:00 GMT") == "2025-11-10"
    assert normalise_date("2025-11-10T08:00:00Z") == "2025-11-10"
    assert normalise_date(None) is None


def test_end_to_end_mock():
    with TestClient(app) as c:
        assert c.get("/api/health").json()["mock"] is True
        r = c.post("/api/verify", json={"text": "The ChatGPT Plus plan costs $20 per month. The latest Python version is 3.12. Paris is in France."})
        assert r.status_code == 200, r.text
        rep = r.json()
        assert rep["results"] and rep["usage"]["llm_calls"] > 0
        b = c.post("/api/briefs", json={"entity": "Acme Corp", "meeting_time": "2026-11-20T10:00:00Z", "purpose": "sales intro"})
        assert b.status_code == 200, b.text
        bid = b.json()["id"]
        assert b.json()["developments"]
        rc = c.post(f"/api/briefs/{bid}/recheck")
        assert rc.status_code == 200 and len(rc.json()["checks"]) == 2
