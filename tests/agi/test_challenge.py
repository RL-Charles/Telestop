"""Tests for the two-mode FastAGI challenge handler."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_reader(lines: list[str]) -> AsyncMock:
    """Build a mock StreamReader that yields predefined lines."""
    reader = AsyncMock()
    reader.readline = AsyncMock(side_effect=[line.encode() for line in lines])
    return reader


def _make_writer() -> MagicMock:
    """Build a mock StreamWriter with an asynchronous drain method."""
    writer = MagicMock()
    writer.drain = AsyncMock()
    return writer


def _agi_env(*args: str) -> list[str]:
    """Return an AGI environment block with positional AGI arguments."""
    lines = [
        "agi_callerid: 5551234567\n",
        "agi_channel: SIP/ht813-fxo-00000001\n",
    ]
    lines.extend(
        f"agi_arg_{index}: {value}\n" for index, value in enumerate(args, 1)
    )
    lines.append("\n")
    return lines


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("trusted", "expected"),
    [(False, "0"), (True, "1")],
)
async def test_check_trusted_sets_channel_flag(trusted: bool, expected: str):
    from agi.challenge import handle

    reader = _make_reader(_agi_env("check_trusted") + ["200 result=1\n"])
    writer = _make_writer()

    with (
        patch("agi.db.is_trusted", new=AsyncMock(return_value=trusted)) as mock_trusted,
        patch("agi.db.add_trusted", new=AsyncMock()) as mock_add,
        patch("agi.db.log_call", new=AsyncMock()) as mock_log,
    ):
        await handle(reader, writer)

        sent = [call.args[0].decode() for call in writer.write.call_args_list]
        assert sent == [f"SET VARIABLE IS_TRUSTED {expected}\n"]
        mock_trusted.assert_awaited_once_with("5551234567")
        mock_log.assert_not_awaited()
        mock_add.assert_not_awaited()


@pytest.mark.asyncio
async def test_log_result_pass_adds_trusted_caller():
    from agi.challenge import handle

    reader = _make_reader(_agi_env("log_result", "PASS"))
    writer = _make_writer()

    with (
        patch("agi.db.is_trusted", new=AsyncMock(return_value=False)),
        patch("agi.db.add_trusted", new=AsyncMock()) as mock_add,
        patch("agi.db.log_call", new=AsyncMock()) as mock_log,
    ):
        await handle(reader, writer)

        writer.write.assert_not_called()
        mock_log.assert_awaited_once_with("5551234567", "PASS")
        mock_add.assert_awaited_once_with("5551234567")


@pytest.mark.asyncio
@pytest.mark.parametrize("result", ["TIMEOUT", "FAIL"])
async def test_log_result_rejection_does_not_add_trusted_caller(result: str):
    from agi.challenge import handle

    reader = _make_reader(_agi_env("log_result", result))
    writer = _make_writer()

    with (
        patch("agi.db.is_trusted", new=AsyncMock(return_value=False)),
        patch("agi.db.add_trusted", new=AsyncMock()) as mock_add,
        patch("agi.db.log_call", new=AsyncMock()) as mock_log,
    ):
        await handle(reader, writer)

        writer.write.assert_not_called()
        mock_log.assert_awaited_once_with("5551234567", result)
        mock_add.assert_not_awaited()


@pytest.mark.asyncio
async def test_log_result_defaults_to_timeout_when_result_is_missing():
    from agi.challenge import handle

    reader = _make_reader(_agi_env("log_result"))
    writer = _make_writer()

    with (
        patch("agi.db.is_trusted", new=AsyncMock(return_value=False)),
        patch("agi.db.add_trusted", new=AsyncMock()) as mock_add,
        patch("agi.db.log_call", new=AsyncMock()) as mock_log,
    ):
        await handle(reader, writer)

        mock_log.assert_awaited_once_with("5551234567", "TIMEOUT")
        mock_add.assert_not_awaited()
