"""Regression tests for reliable offline service startup."""

from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent.parent
ASTERISK_UNIT = REPO_ROOT / "systemd" / "docker-asterisk.service"


def _unit_text() -> str:
    return ASTERISK_UNIT.read_text(encoding="utf-8")


def test_boot_does_not_build_or_pull_container_image() -> None:
    text = _unit_text()
    assert "compose build" not in text
    assert "compose pull" not in text
    assert "compose --ansi never up --no-build" in text


def test_service_uses_deployed_application_directory() -> None:
    assert "WorkingDirectory=/opt/teleblock/app" in _unit_text()


def test_service_recovers_after_clean_container_exit() -> None:
    assert "Restart=always" in _unit_text()
