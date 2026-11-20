# StaleGuard: 2-minute demo script

About 290 spoken words, roughly 150 words a minute. Time codes are targets. Cut the waits in editing (the
streaming check takes 15-25 s live) and keep the first verdicts landing on screen.

## Before you record

1. **Fresh quotas.** Don't run any checks in the 2 minutes before recording (Gemini allows 15 requests/min).
   If Gemini feels slow that day, set `MODEL_FAST=groq/openai/gpt-oss-20b` in `.env` and restart the app.
2. **Restart both**: `scripts\start-bifrost.ps1`, then `scripts\start-app.ps1`. Check the header says
   *Bifrost connected · Tavily ready · budget $… / $1.00 today*.
3. **Pre-build the brief** 10-30 minutes before recording, for a company with recent news (e.g. Nvidia, whose
   CEO change is a strong story). Meeting time: tomorrow. Its chip will be waiting on the Meeting brief tab.
4. **Prepare the bookmarklet shot:** drag *✓ StaleGuard it* to the bookmarks bar. Open a ChatGPT/Claude chat
   (or a plain page) showing an answer that contains stale facts. The sample text below works.
5. Browser zoom 110-125 % so text is readable in the video. Close other tabs.

Sample answer to paste (it is also the app's **Load sample** button):
> OpenAI's flagship model is GPT-4, and ChatGPT Plus costs $20 per month. The newest stable Python release is
> Python 3.11. Twitter's CEO is Parag Agrawal. The EU AI Act is still being negotiated and has not been
> adopted. Stripe was last valued at $95 billion. React's latest major version is React 18.

## Script

| Time | On screen | Say |
|---|---|---|
| 0:00-0:12 | StaleGuard home page | "AI assistants answer from training data that's months or years old, and they sound just as confident about a 2023 price as a law of physics. StaleGuard finds the parts of an answer that have gone stale, and proves it with live sources." |
| 0:12-0:22 | Click **Load sample**, then **Check freshness** | "Here's a typical chatbot answer. StaleGuard pulls out only the claims that can go out of date: versions, prices, who runs what, regulations." |
| 0:22-0:45 | Claims appear underlined with dashed lines; verdicts land one by one; the gauge fills | "Each claim is re-checked on the live web with Tavily: one search for what's true now, one news search for whether it changed. As each check finishes, it lands right in the answer. Green still holds; red is out of date." |
| 0:45-1:00 | Hover **Twitter's CEO is Parag Agrawal**, then **Python 3.11** | "Hover any claim to see what live sources say now, with dated evidence. And the score isn't an LLM's opinion: the model only labels each source. Code computes the score from source age, source authority, and whether newer sources disagree." |
| 1:00-1:10 | Scroll to **Refreshed answer** | "Then it rewrites the answer with every correction marked and sourced." |
| 1:10-1:25 | Tick **Simulate provider outage**, click **Check freshness** again (cut the wait), scroll to the orange fallback banner and open the **Bifrost routing log** | "Every model call goes through Bifrost, with a virtual key that has a daily budget. Here I simulate an outage: the primary model is rejected, and Bifrost falls back to the next provider. No errors, and the routing log shows exactly who served each call and what it cost." |
| 1:25-1:35 | Bookmarklet: select the answer in a chat page, click **✓ StaleGuard it**; the check starts | "It works anywhere: select an answer on any page, click the bookmarklet, and the check starts." |
| 1:35-1:52 | **Meeting brief** tab, open the pre-built brief, click **Re-check now** | "The same engine powers a research agent. It writes a one-page pre-meeting brief from the last 30 days, verifies every development, and re-checks itself automatically before the meeting, logging anything that changed." |
| 1:52-2:00 | Back to the answer view, or a slide with the eval table | "On a held-out set, StaleGuard caught 8 out of 8, including a CEO change from 8 days earlier. StaleGuard: know which parts of an answer you can still trust." |

### Shorter cut (90 s)
Drop the bookmarklet shot (1:25-1:35) and shorten the brief to 10 s.

### If something fails live
- Errors about a **budget**: raise `BIFROST_BUDGET_USD` in `.env` and restart Bifrost.
- Many **unverified** claims: rate limits. Wait a minute and re-run.
- No network: set `STALEGUARD_MOCK=1`. The whole UI flow works with canned data, but say on camera that it's
  offline mode.
