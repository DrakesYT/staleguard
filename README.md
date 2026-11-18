# StaleGuard

**Finds the parts of an AI answer that have gone out of date, checks them against the live web, and gives each claim a freshness score. It also writes meeting briefs and verifies them the same way.**

Built for the Geek Room **Global AI Hackathon**:
- **Primary:** [Tavily] Build a Stale-Answer Detector for AI Applications (uses Tavily + Bifrost)
- **Also covers:** [Tavily] Tavily Research Agent (pre-meeting briefing)

---

## The problem

LLMs answer from training data that is months or years old, and they sound just as confident about a 2023 price as about a law of physics. Users can't tell which sentences are still true. Meeting-prep agents have the same flaw: a brief written yesterday can be wrong by the time the meeting starts.

## What StaleGuard does

**1. Check an AI answer (stale-answer detector)**
Paste any LLM answer. StaleGuard:
1. Extracts only the **time-sensitive claims**: prices, API/model versions, who holds a role, funding, regulations, statistics, "latest X" statements.
2. **Re-checks each claim on the live web** with Tavily (general search plus news search with publication dates).
3. Has a cheap model label each source as *supports / contradicts / unrelated*.
4. Computes a **freshness score (0-100)** with a deterministic, explainable formula (below), and a verdict: `current · aging · disputed · outdated · unverified`.
5. Shows what live sources say now, and produces a **refreshed answer** with corrections marked.

**2. Meeting brief (research agent)**
Enter a company or person plus a meeting time. StaleGuard:
1. Researches the **last 30 days** from five angles (news, funding, launches, hires, partnerships/legal).
2. Writes a **one-page brief**: summary, dated developments with citations, talking points, open questions, watch-outs.
3. **Runs every development through the stale-answer engine**, so each line carries a verdict badge.
4. **Re-checks the brief automatically shortly before the meeting** (default: 90 min before) and logs what changed. You can also re-check manually or print to PDF.

## How the freshness score works

The LLM never makes up the score. It only labels evidence; the score is computed in code (`app/scoring.py`):

- Each claim category has a **half-life**: how quickly that kind of fact goes stale (pricing 45 days, API versions 60, leadership 180, regulation 240, ...).
- A source's weight decays with age relative to that half-life: `weight = 0.5 ^ (age_days / half_life)`. Undated sources get a fixed low weight.
- `freshness = 100 × (0.5 × newest supporting weight + 0.25 × agreement across domains + 0.25 × (1 − contradiction share))`
- A contradiction that is **newer** than the support, or that holds most of the weight, makes the claim **outdated**. A smaller share of contradiction makes it **disputed**. Support from old sources only makes it **aging**.

Every verdict comes with its reasons and the dated evidence, so users can check it themselves.

## Architecture

```
Browser (static HTML/JS)
   │
FastAPI ── pipeline.py ─┬─ claims.py   extract time-sensitive claims ──┐
                        ├─ verify.py   evidence + stance per claim ────┤  all LLM calls
                        ├─ brief.py    30-day research + brief writer ─┤──► Bifrost gateway ──► Gemini / Groq / OpenAI…
                        ├─ scoring.py  deterministic freshness score   │     (fallbacks, routing info, one API)
                        └─ search.py ─────────────────────────────────────► Tavily (general + news, dated)
                         store.py (SQLite) · background pre-meeting re-check loop
```

### How each sponsor technology is used

| | Role in StaleGuard |
|---|---|
| **Tavily** | All live research: claim re-verification (general + `topic=news` for publication dates) and the 30-day meeting research. Publication dates feed the freshness score directly. |
| **Bifrost** | Every LLM call goes through it. **Two-tier routing**: a cheap fast model for claim extraction and stance labelling (most of the calls), a stronger model only for writing the brief and the refreshed answer. **Automatic provider fallback**, so a provider outage doesn't break a check. The UI shows **which provider served each call**, fallbacks used, tokens and estimated cost per run, taken from Bifrost's `routing_info`. |

## Run it

Requirements: Python 3.10+, Node.js 18+ (for Bifrost), a Tavily key, and at least one LLM provider key (Gemini and Groq have free tiers).

```powershell
# 1. Start the gateway, then open http://localhost:8080 and add your provider key(s)
.\scripts\start-bifrost.ps1

# 2. In a second terminal: creates the venv, installs deps, creates .env, starts the app
.\scripts\start-app.ps1
#    put TAVILY_API_KEY in .env, set MODEL_FAST / MODEL_SMART to providers you added

# 3. Open http://localhost:8000
```

**Offline demo:** set `STALEGUARD_MOCK=1` in `.env` to run with canned data and no keys.

**Tests:** `.\.venv\Scripts\python -m pytest -q`

### API

| Method | Path | |
|---|---|---|
| `POST` | `/api/verify` | `{ "text": "...", "as_of": null }` returns a freshness report |
| `POST` | `/api/briefs` | `{ "entity", "meeting_time" (ISO), "purpose" }` returns a verified brief |
| `POST` | `/api/briefs/{id}/recheck` | re-verifies with fresh searches and logs changes |
| `GET` | `/api/briefs`, `/api/briefs/{id}`, `/api/reports/{id}`, `/api/health` | |

Because `/api/verify` is a plain JSON API, any LLM app can send answers through it before showing them to users.

## AI usage disclosure

- **In the product:** LLMs (through Bifrost) extract claims, label evidence, write briefs and rewrite answers. Tavily provides live web data.
- **In development:** built with help from Claude (Anthropic) and Claude Code as coding assistants.

## Team

- Drako (DrakesINC)
