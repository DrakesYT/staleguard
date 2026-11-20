# Accuracy eval

`run_eval.py` sends hand-labelled claims through the same `verify_claim` the app uses (live Tavily search,
LLM stance labels through Bifrost, deterministic scoring) and compares the verdicts with the expected
ones.

```powershell
.\.venv\Scripts\python -m eval.run_eval                 # golden set (19 claims)
.\.venv\Scripts\python -m eval.run_eval --set holdout   # held-out set (8 claims)
.\.venv\Scripts\python -m eval.run_eval --runs 2        # repeat to check stability
```

## Data

- **`golden.json`**: 19 claims used while tuning prompts and scoring. 7 outdated for over a year, 5 that
  went out of date in the last ~18 months, and 7 that are still true.
- **`holdout.json`**: 8 claims written **after** tuning and run once, with no changes made afterwards.
  It includes a CEO resignation 8 days before the eval date (Nvidia, 12 Nov 2026).

Ground truth was checked against live sources on 2026-11-20 and is recorded per claim (`truth`).
Each search query asks for the current state ("UK Prime Minister") and never hints at the answer.

## Results (2026-11-20)

| Set | Claims | Stale-detection accuracy | Strict accuracy |
|---|---|---|---|
| Golden, before tuning | 19 | 18/19 (95%) | 18/19 (95%) |
| Golden, after tuning (2 runs) | 19 | 19/19 (100%) both runs | 19/19 (100%) both runs |
| **Held-out (never tuned on)** | **8** | **8/8 (100%)** | **8/8 (100%)** |

*Stale-detection* checks that the claim was flagged correctly (outdated/disputed vs current/aging). *Strict*
needs the exact verdict.

Live current values the engine found: Kevin Warsh (Fed chair), Andy Burnham (UK PM), Python 3.15,
$159B (Stripe), John Ternus (Apple CEO), interim CEO Colette Kress (Nvidia), Kubernetes v1.37.

Cost: about 1 LLM call and 1.8 Tavily searches per claim, about **$0.001 per claim** at list prices
(free tiers used here).

## What tuning changed (all general rules, none claim-specific)

| Problem seen | Fix |
|---|---|
| Ambiguous neutral query ("X CEO" found Alphabet's X lab and farm news), so no source mentioned Yaccarino leaving | The news search uses the claim text, which finds "...steps down" coverage; the general search keeps the neutral query. Same credit cost. |
| An Oct 2026 article saying "valued at $91.5B **in Feb 2025**, now $159B" was labelled *supports* | Stance rule: a value mentioned only as a past value contradicts. |
| "React 19.3.1" was labelled as contradicting "latest major is React 19" | Stance rule: a more specific value that fits the claim supports it. |
| Tavily dates Wikipedia's Python page **2009** (page creation), so a 2025 blog looked newer | Source authority: dates of maintained reference and docs pages are ignored (see `app/scoring.py`). |
| Free-tier 429s (Gemini 15 req/min, Groq 8k tokens/min) made claims unverified | Bifrost retries with backoff, plus a 4-model fallback chain across separate quota pools. |

## Limits

27 claims is a small sample, and the claims lean towards leadership and version facts, where the web
agrees quickly. Prices with regional variants and numbers that differ by source (valuations, user
counts) are harder and under-represented. Results depend on what the live web says on the day, so
re-running later will give different evidence.
