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


def test_no_relevant_evidence_is_unverified():
    v, _, _ = score("other", [ev("unrelated", 1)], TODAY)
    assert v == "unverified"


def test_parse_json_tolerates_fences_and_chatter():
    assert parse_json('Sure!\n```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('here: {"claims": []} done') == {"claims": []}


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
