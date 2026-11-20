"""Runtime settings, loaded from environment / .env."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _list(value: str | None) -> list[str]:
    return [x.strip() for x in (value or "").split(",") if x.strip()]


@dataclass(frozen=True)
class Settings:
    # Bifrost gateway (OpenAI-compatible). Every LLM call goes through it.
    bifrost_url: str = os.getenv("BIFROST_URL", "http://localhost:8080").rstrip("/")
    # Cheap model: claim extraction + stance judging. Smart model: brief writing + answer refresh.
    model_fast: str = os.getenv("MODEL_FAST", "gemini/gemini-3.5-flash-lite")
    model_smart: str = os.getenv("MODEL_SMART", "groq/openai/gpt-oss-120b")
    # Bifrost tries these in order if the primary provider fails.
    fallbacks: list[str] = field(
        default_factory=lambda: _list(os.getenv(
            "MODEL_FALLBACKS",
            "groq/openai/gpt-oss-120b,gemini/gemini-3.5-flash-lite,groq/openai/gpt-oss-20b,groq/qwen/qwen3.8-27b"))
    )
    # Reasoning models (gpt-oss, Gemini 3.x flash) otherwise spend most of max_tokens thinking.
    reasoning_effort: str = os.getenv("REASONING_EFFORT", "low")
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")
    # STALEGUARD_MOCK=1 runs fully offline with canned search + LLM output (UI dev / demo backup).
    mock: bool = os.getenv("STALEGUARD_MOCK", "0") == "1"
    db_path: Path = Path(os.getenv("DB_PATH", str(ROOT / "data" / "staleguard.db")))
    max_claims: int = int(os.getenv("MAX_CLAIMS", "10"))
    concurrency: int = int(os.getenv("CONCURRENCY", "4"))
    # Auto re-check a brief when its meeting is within this many minutes.
    recheck_window_min: int = int(os.getenv("RECHECK_WINDOW_MIN", "90"))


settings = Settings()
