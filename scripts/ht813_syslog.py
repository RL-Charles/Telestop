#!/usr/bin/env python3
"""
HT813 Syslog Listener — Teleblock diagnostic tool.

Listens for UDP syslog packets from the Grandstream HT813 and prints
them in real-time.  Must be run as root (port 514) or with the
--port flag to use a higher, unprivileged port.

Configure the HT813 web UI first:
  Advanced Settings → Syslog Server  → 192.168.42.1
  Advanced Settings → Syslog Level   → DEBUG (or EXTENDED)
  Advanced Settings → Syslog Server Port → 514  (or match --port)

Usage:
    sudo python3 scripts/ht813_syslog.py              # port 514 (root)
    python3 scripts/ht813_syslog.py --port 5514       # no root needed
    python3 scripts/ht813_syslog.py --filter sip      # show SIP lines only
    python3 scripts/ht813_syslog.py --raw              # raw bytes, no colour
"""
import argparse
import datetime
import socket
import sys
from typing import Optional


# ── ANSI colour helpers ───────────────────────────────────────────────────────
RESET   = "\033[0m"
BOLD    = "\033[1m"
RED     = "\033[31m"
YELLOW  = "\033[33m"
GREEN   = "\033[32m"
CYAN    = "\033[36m"
MAGENTA = "\033[35m"
DIM     = "\033[2m"


def _colour(text: str, code: str, raw: bool) -> str:
    return text if raw else f"{code}{text}{RESET}"


# RFC 3164 severity values (0=EMERG … 7=DEBUG)
SEVERITY_COLOURS = {
    0: RED, 1: RED, 2: RED, 3: RED,
    4: YELLOW, 5: YELLOW,
    6: GREEN, 7: DIM,
}
SEVERITY_NAMES = [
    "EMERG", "ALERT", "CRIT", "ERR",
    "WARNING", "NOTICE", "INFO", "DEBUG",
]


def _parse_priority(raw: bytes) -> tuple[int, int, bytes]:
    """Extract facility/severity from RFC 3164 <PRI> prefix."""
    if raw.startswith(b"<"):
        end = raw.find(b">")
        if end != -1:
            try:
                pri = int(raw[1:end])
                return pri >> 3, pri & 0x07, raw[end + 1:]
            except ValueError:
                pass
    return 1, 6, raw  # default: user-level INFO


def _format_line(
    data: bytes,
    addr: tuple[str, int],
    raw: bool,
    keyword_filter: Optional[str],
) -> Optional[str]:
    """Format one syslog datagram for display.  Returns None if filtered out."""
    facility, severity, rest = _parse_priority(data)
    try:
        message = rest.decode("utf-8", errors="replace").strip()
    except Exception:
        message = repr(rest)

    if keyword_filter and keyword_filter.lower() not in message.lower():
        return None

    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    sev_name = SEVERITY_NAMES[severity] if severity < len(SEVERITY_NAMES) else str(severity)
    sev_colour = SEVERITY_COLOURS.get(severity, "")

    ts_str     = _colour(ts, DIM, raw)
    src_str    = _colour(f"{addr[0]}:{addr[1]}", CYAN, raw)
    sev_str    = _colour(f"{sev_name:<7}", sev_colour, raw)
    msg_str    = message

    # Highlight key SIP / FXO keywords
    if not raw:
        for kw, col in (
            ("INVITE",   BOLD + GREEN),
            ("REGISTER", BOLD + GREEN),
            ("BYE",      BOLD + YELLOW),
            ("RING",     BOLD + MAGENTA),
            ("ERROR",    BOLD + RED),
            ("FAIL",     BOLD + RED),
            ("401",      YELLOW),
            ("403",      RED),
            ("404",      RED),
            ("200 OK",   GREEN),
        ):
            if kw in msg_str:
                msg_str = msg_str.replace(kw, f"{col}{kw}{RESET}")

    return f"{ts_str}  {src_str}  {sev_str}  {msg_str}"


def run(port: int, raw: bool, keyword_filter: Optional[str]) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # Allow multiple listeners on the same port (useful alongside rsyslog)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("0.0.0.0", port))
    except PermissionError:
        sys.exit(
            f"Cannot bind to port {port}: permission denied.\n"
            "Run with sudo, or use --port 5514 (unprivileged)."
        )

    header = (
        f"{'─' * 72}\n"
        f"  HT813 Syslog listener — UDP {port}   "
        f"{'[filter: ' + keyword_filter + ']' if keyword_filter else ''}\n"
        f"  Pi address shown to HT813: 192.168.42.1\n"
        f"  Configure HT813: Advanced Settings → Syslog Server → 192.168.42.1\n"
        f"{'─' * 72}"
    )
    print(_colour(header, CYAN, raw), flush=True)

    while True:
        try:
            data, addr = sock.recvfrom(4096)
            line = _format_line(data, addr, raw, keyword_filter)
            if line is not None:
                print(line, flush=True)
        except KeyboardInterrupt:
            print("\nStopped.", flush=True)
            break
        except Exception as exc:
            print(f"[recv error] {exc}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Real-time HT813 syslog receiver for Teleblock diagnostics.",
    )
    parser.add_argument(
        "--port", type=int, default=514,
        help="UDP port to listen on (default: 514, requires root).",
    )
    parser.add_argument(
        "--filter", dest="keyword_filter", default=None,
        metavar="KEYWORD",
        help="Show only lines containing KEYWORD (case-insensitive).",
    )
    parser.add_argument(
        "--raw", action="store_true",
        help="Disable colour output (plain text).",
    )
    args = parser.parse_args()
    run(args.port, args.raw, args.keyword_filter)


if __name__ == "__main__":
    main()
