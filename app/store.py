"""Tiny SQLite JSON store for reports and briefs."""
from __future__ import annotations

import sqlite3
from typing import TypeVar

from pydantic import BaseModel

from .config import settings

T = TypeVar("T", bound=BaseModel)


def _conn() -> sqlite3.Connection:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(settings.db_path)
    c.execute("CREATE TABLE IF NOT EXISTS items (kind TEXT, id TEXT, created_at TEXT, body TEXT, PRIMARY KEY (kind, id))")
    return c


def save(kind: str, item: BaseModel) -> None:
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO items (kind, id, created_at, body) VALUES (?, ?, ?, ?)",
            (kind, item.id, item.created_at, item.model_dump_json()),
        )


def get(kind: str, item_id: str, model: type[T]) -> T | None:
    with _conn() as c:
        row = c.execute("SELECT body FROM items WHERE kind=? AND id=?", (kind, item_id)).fetchone()
    return model.model_validate_json(row[0]) if row else None


def list_items(kind: str, model: type[T], limit: int = 50) -> list[T]:
    with _conn() as c:
        rows = c.execute(
            "SELECT body FROM items WHERE kind=? ORDER BY created_at DESC LIMIT ?", (kind, limit)
        ).fetchall()
    return [model.model_validate_json(r[0]) for r in rows]
