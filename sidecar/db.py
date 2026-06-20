"""
db.py — StreamGate SQLite session log
Stores every session with duration, amount, and tx hash.
This is your TRACTION PROOF for the judges.
"""

import aiosqlite
import asyncio
from datetime import datetime
from config import DB_PATH


# ── Schema ────────────────────────────────────────────────────────────────────
CREATE_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS sessions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    viewer_id     TEXT    NOT NULL,
    viewer_wallet TEXT    NOT NULL DEFAULT '',
    joined_at     TEXT    NOT NULL,
    parted_at     TEXT,
    duration_sec  REAL    DEFAULT 0,
    rate_per_sec  REAL    NOT NULL,
    amount_usdc   REAL    DEFAULT 0,
    status        TEXT    DEFAULT 'active',   -- active | settled | skipped | failed
    tx_hash       TEXT    DEFAULT '',
    settled_at    TEXT,
    created_at    TEXT    DEFAULT (datetime('now'))
);
"""

CREATE_STATS_TABLE = """
CREATE TABLE IF NOT EXISTS stats (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    total_earned    REAL    DEFAULT 0,
    total_sessions  INTEGER DEFAULT 0,
    updated_at      TEXT    DEFAULT (datetime('now'))
);
"""


async def init_db():
    """Create tables if they don't exist. Call once at startup."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(CREATE_SESSIONS_TABLE)
        await db.execute(CREATE_STATS_TABLE)
        # Seed stats row if empty
        await db.execute(
            "INSERT OR IGNORE INTO stats (id, total_earned, total_sessions) VALUES (1, 0, 0)"
        )
        await db.commit()
    print(f"✅ Database ready at {DB_PATH}")


async def open_session(viewer_id: str, viewer_wallet: str, rate_per_sec: float) -> int:
    """Record a viewer joining. Returns the session row id."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO sessions (viewer_id, viewer_wallet, joined_at, rate_per_sec, status)
            VALUES (?, ?, ?, ?, 'active')
            """,
            (viewer_id, viewer_wallet, datetime.utcnow().isoformat(), rate_per_sec)
        )
        await db.commit()
        return cursor.lastrowid


async def close_session(
    viewer_id: str,
    duration_sec: float,
    amount_usdc: float,
    status: str,        # 'settled' | 'skipped' | 'failed'
    tx_hash: str = ""
):
    """Update the session when a viewer leaves or drops."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE sessions
            SET parted_at    = ?,
                duration_sec = ?,
                amount_usdc  = ?,
                status       = ?,
                tx_hash      = ?,
                settled_at   = ?
            WHERE viewer_id = ? AND status = 'active'
            """,
            (
                datetime.utcnow().isoformat(),
                round(duration_sec, 2),
                round(amount_usdc, 6),
                status,
                tx_hash,
                datetime.utcnow().isoformat() if status == "settled" else None,
                viewer_id,
            )
        )
        # Update running totals
        if status == "settled" and amount_usdc > 0:
            await db.execute(
                """
                UPDATE stats
                SET total_earned   = total_earned + ?,
                    total_sessions = total_sessions + 1,
                    updated_at     = datetime('now')
                WHERE id = 1
                """,
                (amount_usdc,)
            )
        await db.commit()


async def get_stats() -> dict:
    """Return lifetime earnings and session count."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM stats WHERE id = 1") as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else {"total_earned": 0, "total_sessions": 0}


async def get_recent_sessions(limit: int = 20) -> list[dict]:
    """Return recent sessions for the dashboard."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM sessions ORDER BY id DESC LIMIT ?", (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def count_active_sessions() -> int:
    """How many viewers are currently watching."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM sessions WHERE status = 'active'"
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0
