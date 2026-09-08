"""
Teleblock database helpers.
All blocking sqlite3 calls are run in a thread pool executor so the
asyncio event loop is never blocked.
"""
import asyncio
import logging
import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DB_PATH: str = os.getenv("DB_PATH", "/var/lib/teleblock/calls.db")

logger = logging.getLogger(__name__)


def _get_conn() -> sqlite3.Connection:
    path = Path(DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def _apply_schema(conn: sqlite3.Connection) -> None:
    """Create tables if they don't exist yet."""
    schema = Path(__file__).parent.parent / "db" / "schema.sql"
    if schema.exists():
        conn.executescript(schema.read_text())
        conn.commit()


def _ensure_schema() -> None:
    with _get_conn() as conn:
        _apply_schema(conn)


# ---------------------------------------------------------------------------
# Sync helpers (run inside executor)
# ---------------------------------------------------------------------------

def _is_trusted_sync(cid: str) -> bool:
    with _get_conn() as conn:
        _apply_schema(conn)
        row = conn.execute(
            "SELECT 1 FROM trusted_callers WHERE cid = ?", (cid,)
        ).fetchone()
        return row is not None


def _add_trusted_sync(cid: str) -> None:
    with _get_conn() as conn:
        _apply_schema(conn)
        conn.execute(
            """
            INSERT INTO trusted_callers (cid, call_count)
            VALUES (?, 1)
            ON CONFLICT(cid) DO UPDATE SET
                call_count = call_count + 1
            """,
            (cid,),
        )
        conn.commit()


def _log_call_sync(cid: str, result: str) -> None:
    with _get_conn() as conn:
        _apply_schema(conn)
        conn.execute(
            "INSERT INTO calls (cid, result) VALUES (?, ?)",
            (cid, result),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Async public API
# ---------------------------------------------------------------------------

async def is_trusted(cid: str) -> bool:
    """Return True if the caller has previously passed the challenge."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _is_trusted_sync, cid)


async def add_trusted(cid: str) -> None:
    """Record cid as a trusted caller (upsert — increments call_count)."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _add_trusted_sync, cid)


async def log_call(cid: str, result: str) -> None:
    """Append a call record to the calls table."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _log_call_sync, cid, result)
