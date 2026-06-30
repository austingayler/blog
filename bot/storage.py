"""
SQLite-backed persistence for sessions and captured messages.

Schema
------
sessions:
  user_id        INTEGER PRIMARY KEY
  last_activity  REAL    (unix timestamp)
  processing     INTEGER (0/1 bool)

messages:
  id         INTEGER PRIMARY KEY AUTOINCREMENT
  user_id    INTEGER
  timestamp  REAL    (unix timestamp)
  type       TEXT    ("text" | "voice" | "photo")
  content    TEXT    (text body, transcript placeholder, or local file path)
  file_id    TEXT    (Telegram file_id, null for text)
  filename   TEXT    (target filename in the post dir, e.g. image-01.jpg)
"""

import asyncio
import os
import time

import aiosqlite

_DB_PATH: str | None = None
_lock = asyncio.Lock()


def configure(data_dir: str) -> None:
    global _DB_PATH
    os.makedirs(data_dir, exist_ok=True)
    _DB_PATH = os.path.join(data_dir, "voiceblog.db")


async def init() -> None:
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                user_id       INTEGER PRIMARY KEY,
                last_activity REAL    NOT NULL,
                processing    INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS messages (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   INTEGER NOT NULL,
                timestamp REAL    NOT NULL,
                type      TEXT    NOT NULL,
                content   TEXT,
                file_id   TEXT,
                filename  TEXT
            );
        """)
        await db.commit()


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

async def touch_session(user_id: int) -> None:
    """Create or update a session's last_activity to now."""
    now = time.time()
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute("""
            INSERT INTO sessions (user_id, last_activity, processing)
            VALUES (?, ?, 0)
            ON CONFLICT(user_id) DO UPDATE SET
                last_activity = excluded.last_activity,
                processing    = 0
        """, (user_id, now))
        await db.commit()


async def get_active_sessions() -> list[dict]:
    """Return all sessions not currently being processed."""
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM sessions WHERE processing = 0"
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def mark_processing(user_id: int) -> None:
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            "UPDATE sessions SET processing = 1 WHERE user_id = ?", (user_id,)
        )
        await db.commit()


async def delete_session(user_id: int) -> None:
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
        await db.commit()


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

async def add_message(
    user_id: int,
    msg_type: str,
    content: str | None = None,
    file_id: str | None = None,
    filename: str | None = None,
) -> None:
    now = time.time()
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute("""
            INSERT INTO messages (user_id, timestamp, type, content, file_id, filename)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, now, msg_type, content, file_id, filename))
        await db.commit()


async def get_messages(user_id: int) -> list[dict]:
    """Return all messages for a user ordered by timestamp."""
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM messages WHERE user_id = ? ORDER BY timestamp ASC",
            (user_id,),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def update_message_content(msg_id: int, content: str) -> None:
    """Used to store transcript after Whisper processing."""
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute(
            "UPDATE messages SET content = ? WHERE id = ?", (content, msg_id)
        )
        await db.commit()
