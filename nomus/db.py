"""SQLite-хранилище: сессии и обезличенные логи запросов (§7 ТЗ).

Приватность: сырой текст обращения НЕ сохраняется — только SHA-256 хеш
и служебные поля.
"""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from nomus.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    user_id             INTEGER PRIMARY KEY,
    citizenship_profile TEXT DEFAULT 'UNKNOWN',
    risk_profile        TEXT DEFAULT 'UNKNOWN',
    lang                TEXT DEFAULT 'ru',
    disclaimer_ack      INTEGER DEFAULT 0,
    created_at          TIMESTAMP
);

CREATE TABLE IF NOT EXISTS queries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER,
    query_hash    TEXT,
    retrieved_ids TEXT,
    confidence    TEXT,
    red_flag      INTEGER,
    abstained     INTEGER,
    latency_ms    INTEGER,
    created_at    TIMESTAMP
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _conn():
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _conn() as c:
        c.executescript(SCHEMA)


def get_session(user_id: int) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM sessions WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def upsert_session(user_id: int, **fields) -> None:
    allowed = {"citizenship_profile", "risk_profile", "lang", "disclaimer_ack"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    with _conn() as c:
        c.execute(
            "INSERT INTO sessions (user_id, created_at) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO NOTHING",
            (user_id, _now()),
        )
        if fields:
            sets = ", ".join(f"{k} = ?" for k in fields)
            c.execute(f"UPDATE sessions SET {sets} WHERE user_id = ?", (*fields.values(), user_id))


def reset_session(user_id: int) -> None:
    """/reset — очистка профиля (FR-05)."""
    with _conn() as c:
        c.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


def delete_user_data(user_id: int) -> None:
    """/delete — удаление всех данных пользователя (SEC-04)."""
    with _conn() as c:
        c.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        c.execute("DELETE FROM queries WHERE user_id = ?", (user_id,))


def log_query(
    user_id: int,
    query_text: str,
    retrieved_ids: list[str],
    confidence: str,
    red_flag: bool,
    abstained: bool,
    latency_ms: int,
) -> None:
    query_hash = hashlib.sha256(query_text.encode("utf-8")).hexdigest()
    with _conn() as c:
        c.execute(
            "INSERT INTO queries (user_id, query_hash, retrieved_ids, confidence, "
            "red_flag, abstained, latency_ms, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                query_hash,
                json.dumps(retrieved_ids),
                confidence,
                int(red_flag),
                int(abstained),
                latency_ms,
                _now(),
            ),
        )
