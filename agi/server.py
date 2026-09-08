"""
Teleblock FastAGI Server
Listens on 127.0.0.1:4573 for connections from Asterisk.
Each inbound call spawns a handler coroutine.
"""
import asyncio
import logging
import os
from dotenv import load_dotenv

load_dotenv()

AGI_HOST = os.getenv("AGI_HOST", "127.0.0.1")
AGI_PORT = int(os.getenv("AGI_PORT", "4573"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def dispatch(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Route an incoming AGI connection to the correct handler."""
    from agi.challenge import handle  # local import to avoid circular deps
    peer = writer.get_extra_info("peername")
    logger.info("AGI connection from %s", peer)
    try:
        await handle(reader, writer)
    except Exception:
        logger.exception("Unhandled error in AGI handler for %s", peer)
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except (BrokenPipeError, ConnectionResetError, OSError):
            # Asterisk closes the AGI socket as soon as it receives the last
            # command response — that is normal and not an error condition.
            pass
        logger.info("AGI connection closed for %s", peer)


async def main() -> None:
    server = await asyncio.start_server(dispatch, AGI_HOST, AGI_PORT)
    addrs = ", ".join(str(s.getsockname()) for s in server.sockets)
    logger.info("FastAGI server listening on %s", addrs)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
