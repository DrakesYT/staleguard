"""Accuracy eval for the stale-answer engine.

Runs every claim in eval/golden.json through verify_claim (live Tavily + Bifrost, or mock mode)
and prints per-claim results, a confusion table and accuracy.

    .\\.venv\\Scripts\\python -m eval.run_eval              # all claims
    .\\.venv\\Scripts\\python -m eval.run_eval --only fed-powell,uk-pm-starmer
    .\\.venv\\Scripts\\python -m eval.run_eval --runs 2     # repeat to check stability
    .\\.venv\\Scripts\\python -m eval.run_eval --set holdout  # claims never used for tuning

Two accuracy numbers:
- strict: the verdict equals the expected verdict.
- stale-detection: did we flag it the right way? outdated/disputed count as "flagged",
  current/aging as "not flagged". unverified is always wrong.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from app import usage
from app.config import settings
from app.models import Claim
from app.verify import verify_claim

HERE = Path(__file__).resolve().parent
VERDICTS = ["current", "aging", "disputed", "outdated", "unverified"]
FLAGGED = {"outdated", "disputed"}
NOT_FLAGGED = {"current", "aging"}


def lenient_ok(expected: str, got: str) -> bool:
    return got in (FLAGGED if expected == "outdated" else NOT_FLAGGED)


async def run_once(items: list[dict], concurrency: int):
    sem = asyncio.Semaphore(concurrency)

    async def one(it):
        claim = Claim(id=it["id"], text=it["text"], category=it["category"],
                      value=it.get("value", ""), subject=it.get("subject", ""),
                      search_query=it.get("search_query", ""))
        async with sem:
            return it, await verify_claim(claim)

    with usage.track() as u:
        t0 = time.time()
        pairs = await asyncio.gather(*(one(it) for it in items))
        elapsed = time.time() - t0
    return pairs, u, elapsed


def report(pairs, u, elapsed) -> dict:
    print(f"\n{'id':18} {'group':16} {'expected':9} {'got':10} {'fresh':>5}  current value / why")
    print("-" * 110)
    rows = []
    for it, r in pairs:
        strict = r.verdict == it["expected"]
        lenient = lenient_ok(it["expected"], r.verdict)
        mark = "OK " if strict else ("ok~" if lenient else "XX ")
        extra = r.current_value or ""
        if not lenient:
            extra = (r.error or "; ".join(r.reasons[1:]))[:60]
        print(f"{mark} {it['id']:14} {it['group']:16} {it['expected']:9} {r.verdict:10} {r.freshness:5}  {extra[:60]}")
        rows.append({"id": it["id"], "group": it["group"], "expected": it["expected"], "got": r.verdict,
                     "freshness": r.freshness, "strict": strict, "lenient": lenient,
                     "current_value": r.current_value, "reasons": r.reasons, "error": r.error,
                     "evidence": [e.model_dump(include={"domain", "published", "stance", "note"}) for e in r.evidence]})

    # Confusion table: expected (rows) x got (cols)
    conf: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        conf[row["expected"]][row["got"]] += 1
    print(f"\nConfusion (rows = expected, cols = got)\n{'':10}" + "".join(f"{v:>11}" for v in VERDICTS))
    for exp in ("current", "outdated"):
        print(f"{exp:10}" + "".join(f"{conf[exp][v]:>11}" for v in VERDICTS))

    n = len(rows)
    strict = sum(r["strict"] for r in rows)
    lenient = sum(r["lenient"] for r in rows)
    print(f"\nStrict accuracy:          {strict}/{n} = {strict / n:.0%}")
    print(f"Stale-detection accuracy: {lenient}/{n} = {lenient / n:.0%}")
    by_group: dict[str, list[bool]] = defaultdict(list)
    for r in rows:
        by_group[r["group"]].append(r["lenient"])
    for g, oks in by_group.items():
        print(f"  {g:17} {sum(oks)}/{len(oks)}")
    print(f"\nLLM calls {u.llm_calls} · tokens {u.prompt_tokens + u.completion_tokens:,} · est. cost ${u.cost_usd:.4f}"
          f" · fallbacks {u.fallbacks_used} · served by {dict(u.served_by)}"
          f" · Tavily searches {u.tavily_searches} · {elapsed:.0f}s")
    return {"n": n, "strict": strict, "lenient": lenient, "rows": rows,
            "usage": u.model_dump(), "elapsed_s": round(elapsed, 1)}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated claim ids")
    ap.add_argument("--runs", type=int, default=1)
    # Free-tier rate limits (Gemini 15 req/min, Groq 8k tokens/min) make 2 the safe default here.
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--set", default="golden", help="golden (tuned on) or holdout (never tuned on)")
    ap.add_argument("--save", help="results path (default eval/results/<set>.json)")
    args = ap.parse_args()
    args.save = args.save or str(HERE / "results" / f"{args.set}.json")

    golden = json.loads((HERE / f"{args.set}.json").read_text(encoding="utf-8"))
    items = golden["claims"]
    if args.only:
        wanted = set(args.only.split(","))
        items = [it for it in items if it["id"] in wanted]
    print(f"{len(items)} claims · mock={settings.mock} · fast={settings.model_fast} · as_of {golden['as_of']}")

    runs = []
    for i in range(args.runs):
        if args.runs > 1:
            print(f"\n===== run {i + 1}/{args.runs}")
        pairs, u, elapsed = await run_once(items, args.concurrency)
        runs.append(report(pairs, u, elapsed))

    out = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "mock": settings.mock,
           "models": {"fast": settings.model_fast, "fallbacks": settings.fallbacks}, "runs": runs}
    Path(args.save).parent.mkdir(parents=True, exist_ok=True)
    Path(args.save).write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved {args.save}")


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
