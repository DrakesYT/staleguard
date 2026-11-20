"""Data models shared by the API, pipeline and storage."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Category = Literal[
    "pricing", "api_version", "leadership", "funding", "regulation",
    "product", "statistic", "event", "other",
]
Verdict = Literal["current", "aging", "disputed", "outdated", "unverified"]
Stance = Literal["supports", "contradicts", "unrelated"]


class Claim(BaseModel):
    id: str
    text: str
    category: Category = "other"
    subject: str = ""
    value: str = ""          # the time-sensitive value asserted ("$20/month", "v4.2", "Jane Doe")
    search_query: str = ""
    source_urls: list[str] = Field(default_factory=list)  # set for brief claims
    quote: str = ""                # verbatim text from the input the claim came from
    span: list[int] | None = None  # [start, end) of that text in the input, for inline highlighting


class Evidence(BaseModel):
    url: str
    title: str = ""
    snippet: str = ""
    published: str | None = None   # ISO date if known
    domain: str = ""
    stance: Stance = "unrelated"
    note: str = ""


class ClaimResult(BaseModel):
    claim: Claim
    verdict: Verdict
    freshness: int                 # 0-100
    reasons: list[str] = Field(default_factory=list)
    current_value: str = ""        # what the live web says now, if different
    evidence: list[Evidence] = Field(default_factory=list)
    checked_at: str
    error: str = ""                # set when this claim's check failed (search/LLM error)


class CallInfo(BaseModel):
    """One LLM call as Bifrost routed it (shown in the UI's routing log)."""
    task: str
    requested: str                 # provider/model we asked for (the primary)
    served: str                    # provider/model that actually answered
    fallback: bool = False
    ms: int = 0
    tokens: int = 0


class Usage(BaseModel):
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0          # estimate from a local price table
    fallbacks_used: int = 0
    served_by: dict[str, int] = Field(default_factory=dict)   # "provider/model" -> calls
    tavily_searches: int = 0
    cache_hits: int = 0
    calls: list[CallInfo] = Field(default_factory=list)


class VerifyRequest(BaseModel):
    text: str = Field(min_length=20, max_length=20000)
    as_of: str | None = None       # when the answer was generated (optional, informational)
    simulate_outage: bool = False  # demo: point the primary model at an unavailable one so Bifrost falls back


class VerifyReport(BaseModel):
    id: str
    created_at: str
    input_text: str
    as_of: str | None = None
    results: list[ClaimResult]
    overall: int                   # 0-100, mean freshness of checked claims
    summary: dict[str, int]        # verdict -> count
    refreshed_answer: str = ""
    usage: Usage
    simulated_outage: bool = False


class BriefRequest(BaseModel):
    entity: str = Field(min_length=2, max_length=200)
    meeting_time: str               # ISO datetime
    purpose: str = Field(default="", max_length=500)
    simulate_outage: bool = False


class Source(BaseModel):
    n: int
    url: str
    title: str = ""
    snippet: str = ""
    published: str | None = None
    domain: str = ""


class BriefContent(BaseModel):
    one_liner: str = ""
    talking_points: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    watch_outs: list[str] = Field(default_factory=list)


class CheckEvent(BaseModel):
    at: str
    trigger: Literal["created", "manual", "pre_meeting"]
    changes: list[str] = Field(default_factory=list)


class Brief(BaseModel):
    id: str
    entity: str
    purpose: str = ""
    meeting_time: str
    created_at: str
    sources: list[Source]
    content: BriefContent
    developments: list[ClaimResult]
    checks: list[CheckEvent] = Field(default_factory=list)
    pre_meeting_checked: bool = False
    usage: Usage
