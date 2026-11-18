"""StaleGuard API + static frontend."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import pipeline, store
from .config import settings
from .llm import LLMError
from .models import Brief, BriefRequest, VerifyReport, VerifyRequest
from .search import SearchError

log = logging.getLogger("staleguard")
STATIC = Path(__file__).resolve().parent.parent / "static"


async def _pre_meeting_loop():
    """Every 5 minutes, re-check briefs whose meeting starts within RECHECK_WINDOW_MIN."""
    while True:
        try:
            for b in await pipeline.due_for_pre_meeting():
                log.info("pre-meeting re-check for brief %s (%s)", b.id, b.entity)
                await pipeline.recheck_brief(b, trigger="pre_meeting")
        except Exception:  # never let the loop die
            log.exception("pre-meeting loop error")
        await asyncio.sleep(300)


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(_pre_meeting_loop())
    yield
    task.cancel()


app = FastAPI(title="StaleGuard", version="0.1.0", lifespan=lifespan)


def _fail(e: Exception) -> HTTPException:
    if isinstance(e, (LLMError, SearchError)):
        return HTTPException(status_code=502, detail=str(e))
    log.exception("unhandled error")
    return HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@app.get("/api/health")
async def health():
    bifrost_ok = settings.mock
    if not settings.mock:
        try:
            async with httpx.AsyncClient(timeout=3) as c:
                bifrost_ok = (await c.get(settings.bifrost_url)).status_code < 500
        except httpx.HTTPError:
            bifrost_ok = False
    return {
        "mock": settings.mock,
        "bifrost": {"url": settings.bifrost_url, "reachable": bifrost_ok},
        "tavily_key_set": bool(settings.tavily_api_key) or settings.mock,
        "models": {"fast": settings.model_fast, "smart": settings.model_smart, "fallbacks": settings.fallbacks},
    }


@app.post("/api/verify", response_model=VerifyReport)
async def verify(req: VerifyRequest):
    try:
        return await pipeline.verify_answer(req.text, req.as_of)
    except Exception as e:
        raise _fail(e)


@app.get("/api/reports/{report_id}", response_model=VerifyReport)
async def get_report(report_id: str):
    r = store.get("report", report_id, VerifyReport)
    if not r:
        raise HTTPException(404, "report not found")
    return r


@app.post("/api/briefs", response_model=Brief)
async def create_brief(req: BriefRequest):
    try:
        return await pipeline.create_brief(req.entity, req.meeting_time, req.purpose)
    except Exception as e:
        raise _fail(e)


@app.get("/api/briefs", response_model=list[Brief])
async def list_briefs():
    return store.list_items("brief", Brief, limit=30)


@app.get("/api/briefs/{brief_id}", response_model=Brief)
async def get_brief(brief_id: str):
    b = store.get("brief", brief_id, Brief)
    if not b:
        raise HTTPException(404, "brief not found")
    return b


@app.post("/api/briefs/{brief_id}/recheck", response_model=Brief)
async def recheck(brief_id: str):
    b = store.get("brief", brief_id, Brief)
    if not b:
        raise HTTPException(404, "brief not found")
    try:
        return await pipeline.recheck_brief(b, trigger="manual")
    except Exception as e:
        raise _fail(e)


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")
