"""
Challenge AGI handler — two modes selected by the first AGI argument:

  check_trusted  — DB lookup only; sets IS_TRUSTED=1 on the channel if the
                   caller has passed before.  Called before Read() so no DTMF
                   or audio FD polling occurs.

  log_result     — Reads CHALLENGE_RESULT set by the dialplan, logs to DB,
                   and adds caller to trusted_callers on first PASS.

All DTMF collection and call routing is done in pure Asterisk dialplan
(via Read() + GotoIf) to avoid the ast_waitfordigit_full FD race condition
that causes immediate TIMEOUT when the AGI issues WAIT FOR DIGIT.
"""
import asyncio
import logging

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


async def _readline(reader: asyncio.StreamReader) -> str:
    line = await reader.readline()
    return line.decode().rstrip("\n")


async def _send(writer: asyncio.StreamWriter, cmd: str) -> None:
    writer.write((cmd + "\n").encode())
    await writer.drain()


async def _read_agi_env(reader: asyncio.StreamReader) -> dict[str, str]:
    """Read the initial AGI environment variable block."""
    env: dict[str, str] = {}
    while True:
        line = await _readline(reader)
        if not line:
            break
        if line.startswith("agi_"):
            key, _, value = line.partition(": ")
            env[key] = value
    return env


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    from agi.db import is_trusted, add_trusted, log_call

    env = await _read_agi_env(reader)
    caller = env.get("agi_callerid", "unknown")
    mode = env.get("agi_arg_1", "log_result")

    if mode == "check_trusted":
        trusted = await is_trusted(caller)
        logger.info("%s trusted=%s", caller, trusted)
        flag = "1" if trusted else "0"
        await _send(writer, f"SET VARIABLE IS_TRUSTED {flag}")
        await _readline(reader)  # consume response

    else:  # log_result
        # CHALLENGE_RESULT is passed as agi_arg_2 by the dialplan.
        # Channel variables set via Set() are not included in the AGI env
        # block, so we pass the value as an explicit argument instead.
        result = env.get("agi_arg_2", "TIMEOUT").strip()
        logger.info("%s result=%s", caller, result)
        await log_call(caller, result)
        if result == "PASS":
            await add_trusted(caller)
        # No further commands — AGI exits cleanly
