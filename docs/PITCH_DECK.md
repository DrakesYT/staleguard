# StaleGuard: pitch deck content (7 slides)

Each slide lists the **on-slide text** (keep it this short), a **visual**, and **speaker notes**. The table at the
end maps slides to the judging criteria.

---

## 1 · Title

**On slide**
- **StaleGuard**
- Know which parts of an AI answer you can still trust.
- Tavily Stale-Answer Detector · + Tavily Research Agent · Built with Tavily + Bifrost
- Drako · Geek Room Global AI Hackathon 2026

**Visual:** screenshot of the annotated answer, with red and green underlines and the hover popover open on
"Twitter's CEO is Parag Agrawal → Now: Elon Musk".

**Notes:** One sentence: StaleGuard finds the out-of-date sentences in an AI answer, proves it with live dated
sources, and fixes them.

---

## 2 · The problem

**On slide**
- LLMs answer from a training snapshot and sound equally sure about everything.
- Asked today, a model may still say:
  - "Jerome Powell chairs the Fed" (changed May 2026)
  - "The newest Python is 3.14" (changed Oct 2026)
  - "Tim Cook is Apple's CEO" (changed Sep 2026)
- Users can't tell which sentences expired. Neither can the apps built on these models.
- Meeting briefs go stale too: written yesterday, wrong at 10 am.

**Visual:** a chatbot answer with three sentences quietly crossed out in red.

**Notes:** Stale answers aren't hallucinations: they *were* true. That makes them harder to spot, because they
look plausible and often have sources. The cost lands on anyone acting on them: sales calls, support answers,
dev docs, finance.

---

## 3 · The solution

**On slide**
1. Extract only the **time-sensitive claims** (prices, versions, roles, funding, rules, "latest X")
2. **Re-check each one on the live web** (Tavily: what's true now + did it change?)
3. **Score freshness in code**, not by the LLM: current · aging · disputed · outdated
4. **Show it in place**: your answer, underlined by verdict, streaming live; hover for evidence
5. **Fix it**: a refreshed answer with every correction sourced

Works on any page (bookmarklet) and via a JSON/SSE API, so any LLM app can check its answers before users see them.

**Visual:** 3 screenshots side by side: streaming check, hover popover, refreshed answer.

**Notes:** Mention the second product here: the same engine powers a research agent that writes a 30-day
pre-meeting brief, verifies every line, and re-checks itself shortly before the meeting.

---

## 4 · How it works

**On slide:** the architecture diagram (`docs/architecture.svg`) and one line under it:
*The LLM labels evidence; code computes the score.*

**Visual:** `docs/architecture.svg`.

**Notes:** Walk it top to bottom.
- Three entry points: answer check, meeting brief, bookmarklet.
- Five pipeline stages. The cheap model does the bulk work (extraction, labelling); the smart model only
  writes (brief, refreshed answer).
- Tavily on one side, Bifrost on the other. Every model call carries a Bifrost virtual key.

---

## 5 · A score you can audit, and proof it works

**On slide**
- `weight = recency (half-life by category) × source authority`
  - pricing 45 d · versions 60 d · leadership 180 d · regulation 240 d
  - official/gov ×1.5 · docs ×1.4 · major news ×1.2 · user-generated ×0.6
- `freshness = 100 × (0.5 strongest support + 0.25 agreement + 0.25 (1 − contradiction))`
- Every verdict shows its reasons and dated sources

| Eval (live web, Nov 2026) | Result |
|---|---|
| 19 labelled claims (tuning set) | 19/19, on 2 runs |
| **8 held-out claims, never tuned on** | **8/8** |
| includes Nvidia's CEO change from **8 days** earlier | caught, interim CEO named |

**Visual:** the table, plus a claim card with "Why" expanded, showing reasons like *"Dates ignored for maintained
pages (search engines report their creation date): wikipedia.org"*.

**Notes:**
- Two engineering details judges will appreciate:
  - (1) Search engines date Wikipedia and docs pages by when they were *created* (Tavily dates Wikipedia's Python page 2009), so StaleGuard ignores those dates instead of being fooled.
  - (2) A neutral query like "X CEO" is ambiguous, so a second news search on the claim itself finds "steps down" coverage.
- Be upfront: 27 claims is a small eval, focused on leadership and versions.

---

## 6 · Tavily + Bifrost, and what each one does

**On slide**

**Tavily: the evidence**
- General search for the current state + `topic=news` search on the claim for change coverage
- Published dates on every source feed the score
- 30-day, five-angle research for briefs

**Bifrost: the reliable, budgeted model layer**
- **Virtual key** on every call · **$1/day budget** · **600 req/h** rate limit (402 when spent)
- **Fallback chain** across 4 models with separate quotas + retry with backoff on 429s
- **Two-tier routing**: cheap model for most calls, smart model only for writing
- **Routing log** in the UI: requested vs served model, fallback, tokens, time, plus live budget

**Visual:** screenshot of the usage panel after a **simulated outage**: the orange "Bifrost fallback × 9" banner,
the routing log table, and the budget bar.

**Notes:** The outage toggle asks for a model the provider has retired. That's a real rejection, not a mock, and
Bifrost recovers without errors. In testing, the fallback chain also absorbed genuine free-tier rate limits.

---

## 7 · Impact, scale, next

**On slide**
- **Cost:** about $0.001 per claim · about $0.008 per answer (list prices)
- **Drop-in:** `POST /api/verify` (or the SSE stream) before showing any LLM answer
- **Scales out:** stateless API · search cache · per-key budgets and rate limits in Bifrost · Postgres instead of SQLite for multi-user
- **Next:** browser extension that marks stale claims inline on chatbot pages · per-domain authority learned
  from eval data · Slack/email delivery of re-checked briefs

**Visual:** a single line of code: `report = POST /api/verify {"text": answer}`, then a verdict badge.

**Notes:**
- Who it's for:
  - teams shipping LLM features that need answers with a "checked against the live web today" stamp;
  - analysts and salespeople preparing for meetings.
- Close with the tagline: *Know which parts of an AI answer you can still trust.*

---

## Judging criteria coverage

| Criterion | Where it lands |
|---|---|
| Innovation | Slides 3, 5: stale ≠ hallucination; claim-level freshness with living-document date handling |
| Technical execution | Slides 4, 5: deterministic tested score, streaming SSE, eval with a held-out set, 22 tests |
| Problem / impact | Slides 2, 7: real recent changes models miss; drop-in API |
| Use of AI | Slides 4, 6: two-tier models through Bifrost; the LLM labels, code decides |
| UX | Slides 1, 3: inline highlights, live streaming, hover evidence, bookmarklet |
| Scalability | Slides 6, 7: budgets, rate limits, fallback across providers, stateless API |
