"""
Config sanity tests for the Asterisk dialplan and PJSIP configuration.

These tests parse the static config files directly — no Asterisk process,
no mocking, no network required.  They act as a regression guard: if
extensions.conf or pjsip.conf is edited in a way that would break outbound
calling or the inbound challenge flow, these tests fail immediately.

Run: pytest tests/asterisk/test_dialplan.py -v
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# ── Paths ──────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent.parent
EXTENSIONS_CONF = REPO_ROOT / "asterisk" / "extensions.conf"
PJSIP_CONF = REPO_ROOT / "asterisk" / "pjsip.conf"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _section_body(text: str, section: str) -> str:
    """
    Return the text body of `[section]` up to (but not including) the next
    section header or end of file.  Returns empty string if section not found.
    """
    pattern = re.compile(
        r"^\[" + re.escape(section) + r"\][^\n]*\n(.*?)(?=^\[|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    return match.group(1) if match else ""


def _sections(text: str) -> list[str]:
    """Return all section names found in an Asterisk-style config file."""
    return re.findall(r"^\[([^\]]+)\]", text, re.MULTILINE)


# ═══════════════════════════════════════════════════════════════════════════════
# extensions.conf — [from-internal] (outbound)
# ═══════════════════════════════════════════════════════════════════════════════

class TestFromInternal:
    """Verify the outbound dialplan context is correctly defined."""

    def test_section_exists(self) -> None:
        """[from-internal] context must be present in extensions.conf."""
        assert "from-internal" in _sections(_read(EXTENSIONS_CONF)), (
            "[from-internal] context is missing from extensions.conf — "
            "the house phone cannot dial out without it"
        )

    def test_permissive_pattern_present(self) -> None:
        """Accept dialable characters without swallowing special extensions."""
        body = _section_body(_read(EXTENSIONS_CONF), "from-internal")
        outbound_pattern = re.escape("_[0-9*#+a-zA-Z].")
        assert re.search(r"exten\s*=>\s*" + outbound_pattern, body), (
            "[from-internal] has no permissive outbound pattern — "
            "dialled numbers will not match any extension and calls will fail"
        )

    def test_dials_fxo_endpoint(self) -> None:
        """The Dial() target must use the correct PJSIP trunk format: PJSIP/${EXTEN}@ht813-fxo.
        Using PJSIP/ht813-fxo/${EXTEN} passes the number as a raw URI and fails."""
        body = _section_body(_read(EXTENSIONS_CONF), "from-internal")
        # Correct format: PJSIP/<number>@ht813-fxo  (trunk dial via endpoint)
        assert re.search(r"Dial\s*\(\s*PJSIP/[^,]+@ht813-fxo", body), (
            "[from-internal] Dial() is not using PJSIP/${EXTEN}@ht813-fxo format — "
            "PJSIP/ht813-fxo/${EXTEN} produces 'invalid URI' errors; use PJSIP/${EXTEN}@ht813-fxo"
        )

    def test_no_agi_challenge_in_outbound(self) -> None:
        """Outbound context must NOT invoke the AGI challenge — that's inbound only."""
        body = _section_body(_read(EXTENSIONS_CONF), "from-internal")
        assert "AGI(" not in body, (
            "[from-internal] contains an AGI() call — the challenge must only "
            "run on inbound calls; removing it from the outbound context"
        )

    def test_hangup_present(self) -> None:
        """Context must end with Hangup() to clean up after the call."""
        body = _section_body(_read(EXTENSIONS_CONF), "from-internal")
        assert "Hangup()" in body, (
            "[from-internal] is missing Hangup() — channels may be left dangling"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# extensions.conf — [from-pstn] (inbound — regression guard)
# ═══════════════════════════════════════════════════════════════════════════════

class TestFromPstn:
    """Verify the inbound challenge context wasn't accidentally broken."""

    def test_section_exists(self) -> None:
        assert "from-pstn" in _sections(_read(EXTENSIONS_CONF)), (
            "[from-pstn] context is missing — inbound calls will be rejected"
        )

    def test_agi_challenge_present(self) -> None:
        body = _section_body(_read(EXTENSIONS_CONF), "from-pstn")
        assert "AGI(" in body, (
            "[from-pstn] is missing AGI() call — inbound challenge won't run"
        )

    def test_routes_to_allow_on_pass(self) -> None:
        body = _section_body(_read(EXTENSIONS_CONF), "from-pstn")
        assert re.search(r"CHALLENGE_RESULT.*PASS", body), (
            "[from-pstn] does not route PASS result to [allow] — "
            "callers who pass the challenge won't connect"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# extensions.conf — [allow] and [block]
# ═══════════════════════════════════════════════════════════════════════════════

class TestAllowBlock:
    def test_allow_dials_house_phone(self) -> None:
        body = _section_body(_read(EXTENSIONS_CONF), "allow")
        assert re.search(r"Dial\s*\(\s*PJSIP/house-phone", body), (
            "[allow] does not Dial() PJSIP/house-phone — "
            "callers who pass the challenge won't reach the analogue phone"
        )

    def test_block_plays_message(self) -> None:
        body = _section_body(_read(EXTENSIONS_CONF), "block")
        assert "Playback(" in body, (
            "[block] is missing Playback() — blocked callers get silence"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# pjsip.conf — ht813-fxo endpoint (FXO / PSTN side)
# ═══════════════════════════════════════════════════════════════════════════════

def _pjsip_endpoint_body(section: str) -> str:
    """Return the body of the first type=endpoint block for a given section name."""
    text = _read(PJSIP_CONF)
    # A section may appear multiple times (aor, auth, endpoint) — find the endpoint one.
    pattern = re.compile(
        r"^\[" + re.escape(section) + r"\][^\n]*\n(.*?)(?=^\[|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    for match in pattern.finditer(text):
        body = match.group(1)
        if "type=endpoint" in body:
            return body
    return ""


def _pjsip_aor_body(section: str) -> str:
    """Return the body of the first type=aor block for a section."""
    text = _read(PJSIP_CONF)
    pattern = re.compile(
        r"^\[" + re.escape(section) + r"\][^\n]*\n(.*?)(?=^\[|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    for match in pattern.finditer(text):
        body = match.group(1)
        if "type=aor" in body:
            return body
    return ""


class TestPjsipFxo:
    def test_ht813_fxo_endpoint_exists(self) -> None:
        assert "ht813-fxo" in _sections(_read(PJSIP_CONF)), (
            "[ht813-fxo] is missing from pjsip.conf — FXO trunk not configured"
        )

    def test_outbound_auth_set(self) -> None:
        body = _pjsip_endpoint_body("ht813-fxo")
        assert re.search(r"outbound_auth\s*=", body), (
            "[ht813-fxo] endpoint is missing outbound_auth — outbound INVITEs "
            "will fail if the HT813 responds with a 401 challenge"
        )

    def test_direct_peer_has_static_contact(self) -> None:
        body = _pjsip_aor_body("ht813-fxo")
        assert re.search(r"^contact\s*=\s*sip:.*:5062\s*$", body, re.MULTILINE), (
            "[ht813-fxo] has no static FXO contact — direct-IP peers with SIP "
            "registration disabled remain unavailable after Asterisk restarts"
        )

    def test_inbound_context_is_from_pstn(self) -> None:
        body = _pjsip_endpoint_body("ht813-fxo")
        assert re.search(r"context\s*=\s*from-pstn", body), (
            "[ht813-fxo] endpoint context is not from-pstn — "
            "inbound PSTN calls will land in the wrong dialplan context"
        )

    def test_ulaw_only(self) -> None:
        body = _pjsip_endpoint_body("ht813-fxo")
        assert re.search(r"allow\s*=\s*ulaw", body), (
            "[ht813-fxo] does not restrict codec to ulaw — G.729 or other codecs "
            "may be negotiated, causing audio problems"
        )

    def test_direct_media_disabled(self) -> None:
        body = _pjsip_endpoint_body("ht813-fxo")
        assert re.search(r"direct_media\s*=\s*no", body), (
            "[ht813-fxo] has direct_media enabled — forces RTP through the Pi "
            "which is required for AGI audio to work"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# pjsip.conf — house-phone endpoint (FXS / analogue phone side)
# ═══════════════════════════════════════════════════════════════════════════════

class TestPjsipHousePhone:
    def test_house_phone_endpoint_exists(self) -> None:
        assert "house-phone" in _sections(_read(PJSIP_CONF)), (
            "[house-phone] is missing from pjsip.conf — the FXS analogue phone "
            "cannot peer with Asterisk and no outbound calls can originate"
        )

    def test_direct_peer_has_static_contact(self) -> None:
        body = _pjsip_aor_body("house-phone")
        assert re.search(r"^contact\s*=\s*sip:.*:5060\s*$", body, re.MULTILINE), (
            "[house-phone] has no static FXS contact — direct-IP peers with SIP "
            "registration disabled remain unavailable after Asterisk restarts"
        )

    def test_context_is_from_internal(self) -> None:
        body = _pjsip_endpoint_body("house-phone")
        assert re.search(r"context\s*=\s*from-internal", body), (
            "[house-phone] endpoint context is not from-internal — "
            "outbound calls from the analogue phone will land in the wrong context"
        )

    def test_ulaw_only(self) -> None:
        body = _pjsip_endpoint_body("house-phone")
        assert re.search(r"allow\s*=\s*ulaw", body), (
            "[house-phone] does not restrict codec to ulaw"
        )
