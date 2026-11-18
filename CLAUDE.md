# StaleGuard: project guide for Claude Code

Hackathon entry: Geek Room Global AI Hackathon. **Hard deadline: 21 Nov 2026, 11:59 PM IST (11:29 PM Karachi).**
Solo dev (Drako) + Claude Code. Windows machine, PowerShell. Judging: innovation, technical execution,
problem/impact, use of AI, UX, scalability.

Primary problem statement: **[Tavily] Stale-Answer Detector** (must use Tavily AND Bifrost).
Secondary: **[Tavily] Research Agent** (one-page pre-meeting brief, last 30 days, source-backed).
The brief is a showcase consumer of the stale-answer engine: every brief development is verified.

## Run
- Gateway: `.\scripts\start-bifrost.ps1` → http://localhost:8080 (add provider keys in its UI)
- App: `.\scripts\start-app.ps1` → http://localhost:8000
- Offline: `STALEGUARD_MOCK=1` in `.env` (no keys needed, deterministic)
- Tests: `.\.venv\Scripts\python -m pytest -q` (run in mock mode automatically)

## Layout
- `app/llm.py`: ONLY place that calls an LLM. Goes through Bifrost `/v1/chat/completions` with `fallbacks`; records usage + `extra_fields.routing_info`.
- `app/search.py`: ONLY place that calls Tavily. Normalises dates to YYYY-MM-DD; 10-min cache, `fresh=True` bypasses.
- `app/claims.py`: claim extraction prompt. `app/verify.py`: evidence + stance per claim.
- `app/scoring.py`: deterministic freshness score. The LLM must never produce the score. Covered by tests.
- `app/brief.py`: 30-day research + brief writer. `app/pipeline.py`: orchestration, re-check, pre-meeting scheduling.
- `app/mock.py`: offline stand-ins, keyed by the `task=` label passed to `llm.chat`.
- `static/`: vanilla HTML/CSS/JS, no build step. Keep it that way.

## Conventions
- Every new LLM call: go through `llm.chat`/`llm.chat_json` with a `task=` label, and add a mock branch in `mock.py`.
- Cheap model (`smart=False`) by default; `smart=True` only for long-form writing.
- Keep the score explainable: any new factor must add a human-readable line to `reasons`.
- Run pytest after changes. Don't commit `.env`.

## Status (18 Nov)
DONE: full pipeline, API, UI (both tabs), mock mode, 8 passing tests, README.

## Remaining plan
Thu 19:
1. Real-key smoke test: Bifrost up, Gemini/Groq keys added, Tavily key. Run the sample answer + a real company brief.
2. Tune prompts on real output (claim extraction recall/precision, stance accuracy). Adjust half-lives if verdicts feel off.
3. Show the fallback for the demo: set primary to a provider with a deliberately wrong key so Bifrost falls back; the UI shows "Fallbacks 1" and the serving provider.

Fri 20:
4. Nice-to-haves, only if the core is solid: highlight claims inline in the pasted answer; "as_of" date input; small browser bookmarklet/extension that sends selected text to `/api/verify`; Bifrost virtual key with a budget cap.
5. Deploy option (optional): Render/Railway for the app; Bifrost needs to run alongside it (Docker). Skip if risky; a demo video is enough.

Sat 21 (submit by ~9 PM PKT, not 11 PM):
6. Public GitHub repo, README final, screenshots/GIF.
7. Pitch deck: problem, solution, architecture, how Tavily + Bifrost each contribute, live prototype screenshots, scoring formula.
8. 2-3 min demo video: paste stale answer → outdated badges + refreshed answer → build brief → re-check shows changes → usage panel (routing/fallback/cost).
9. Star github.com/maximhq/bifrost (mandatory), join Discord, fill the Google Form ONCE: Track = Tavily (confirm on Discord), tick both Tavily statements.
