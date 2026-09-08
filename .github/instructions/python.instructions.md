---
applyTo: "**/*.py"
description: "Python coding standards for the Teleblock project. Use when writing or reviewing Python code."
---

# Python Standards — Teleblock

## Style
- Follow **PEP 8**; line length ≤ 100 characters
- Use **type annotations** on all public functions, methods, and module-level variables
- Use **f-strings** exclusively; no `%`-formatting or `.format()` in new code
- Prefer `pathlib.Path` over `os.path` for all file system operations
- Use `dataclasses` or `pydantic` models for structured data (call records, config)

## Async Patterns
- The FastAGI server (`agi/server.py`) uses `asyncio`; all AGI handlers must be `async def`
- Use `asyncio.timeout()` (Python 3.11+) for call timeouts — not `asyncio.wait_for()` wrapping deprecated patterns
- Do **not** use `asyncio.get_event_loop()` — use `asyncio.get_running_loop()` or `asyncio.run()`

## Database (SQLite)
- All queries must use **parameterised placeholders** (`?`) — never f-string or concatenated SQL
- Use `sqlite3.Row` factory to retrieve rows as dicts
- Wrap write operations in `with conn:` context manager for auto-commit/rollback
- Schema is in `db/schema.sql`; run migrations with `scripts/migrate.py`

## Logging
```python
import logging
logger = logging.getLogger(__name__)
# Use module-level logger, not root logger
# Levels: DEBUG for AGI variable dumps, INFO for call events, WARNING for screener decisions, ERROR for exceptions
```

## Configuration
```python
from dotenv import load_dotenv
import os
load_dotenv()
AMI_HOST = os.getenv("AMI_HOST", "127.0.0.1")
```
- All tuneable values live in `.env`; document them in `.env.example`
- Never use `os.environ[]` (raises on missing key) — use `os.getenv()` with a safe default

## Testing
- Use `pytest` with `pytest-asyncio` for async tests
- Mock Asterisk AMI/AGI with `unittest.mock.AsyncMock`
- Test files mirror the source tree: `agi/screener.py` → `tests/agi/test_screener.py`
- Minimum coverage target: **80%** on `agi/` and `scripts/`; run `pytest --cov=agi --cov=scripts`

## Error Handling
- Catch specific exceptions — never bare `except:` or `except Exception:` without re-raise or logging
- AGI scripts must gracefully `HANGUP` the channel on unhandled errors to avoid stuck calls
- Use custom exception classes in `teleblock/exceptions.py` for domain errors

## Security
- Strip and validate all data read from Asterisk channel variables before use
- Caller ID may be logged and stored in full — plain-text CID is intentional on this single-owner DIY device
- Use `secrets` module (not `random`) for any token generation
