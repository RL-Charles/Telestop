#!/usr/bin/env python3
"""
Teleblock stack health verification script.

Checks:
  1. Docker container 'asterisk' is running
  2. Asterisk core is alive (docker exec)
  3. PJSIP endpoints are loaded
  4. FastAGI TCP port is reachable (127.0.0.1:4573)
  5. SQLite DB exists and has the correct schema
  6. Call log summary (row counts by result)

Usage:
    python3 scripts/verify.py
    python3 scripts/verify.py --no-docker   # skip Docker checks (bare-metal Asterisk)
"""
import argparse
import socket
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

# ── Colour helpers ────────────────────────────────────────────────────────────
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
RESET = "\033[0m"

PASS = f"{GREEN}PASS{RESET}"
FAIL = f"{RED}FAIL{RESET}"
WARN = f"{YELLOW}WARN{RESET}"
SKIP = f"{YELLOW}SKIP{RESET}"

ROW_WIDTH = 60


def _row(label: str, status: str, detail: str = "") -> None:
    dots = "." * max(2, ROW_WIDTH - len(label))
    detail_str = f"  {detail}" if detail else ""
    print(f"  {label}{dots}{status}{detail_str}")


# ── Check functions ────────────────────────────────────────────────────────────

def check_docker_running() -> bool:
    """Confirm the 'asterisk' Docker container is in Running state."""
    try:
        result = subprocess.run(
            ["sudo", "docker", "inspect", "--format", "{{.State.Running}}", "asterisk"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        running = result.stdout.strip() == "true"
        _row("Docker container 'asterisk' running", PASS if running else FAIL,
             "" if running else result.stderr.strip() or "container not found")
        return running
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        _row("Docker container 'asterisk' running", FAIL, str(exc))
        return False


def check_asterisk_core() -> bool:
    """Run 'core show version' inside the container."""
    try:
        result = subprocess.run(
            ["sudo", "docker", "exec", "asterisk",
             "asterisk", "-rx", "core show version"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        ok = result.returncode == 0 and "Asterisk" in result.stdout
        detail = result.stdout.strip().splitlines()[0] if ok else result.stderr.strip()
        _row("Asterisk core responding", PASS if ok else FAIL, detail)
        return ok
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        _row("Asterisk core responding", FAIL, str(exc))
        return False


def check_pjsip_endpoints() -> bool:
    """Check that PJSIP endpoint list contains ht813-fxo."""
    try:
        result = subprocess.run(
            ["sudo", "docker", "exec", "asterisk",
             "asterisk", "-rx", "pjsip show endpoints"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        output = result.stdout
        has_endpoint = "ht813-fxo" in output
        # Extract the endpoint line for the detail
        detail_line = next(
            (ln.strip() for ln in output.splitlines() if "ht813-fxo" in ln), ""
        )
        _row("PJSIP endpoint ht813-fxo loaded", PASS if has_endpoint else WARN,
             detail_line or "endpoint not found — check pjsip.conf")
        return has_endpoint
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        _row("PJSIP endpoint ht813-fxo loaded", FAIL, str(exc))
        return False


def check_pjsip_contact() -> bool:
    """Check the HT813 contact state (Avail = registered, else Unreachable)."""
    try:
        result = subprocess.run(
            ["sudo", "docker", "exec", "asterisk",
             "asterisk", "-rx", "pjsip show contacts"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        output = result.stdout
        if "ht813-fxo" not in output:
            _row("HT813 SIP contact state", WARN, "no contact row — HT813 not registered yet")
            return False
        # NonQual = qualify disabled (normal for static contacts); Avail = qualify active and passing
        contact_line = next(
            (ln.strip() for ln in output.splitlines() if "ht813-fxo" in ln and "Contact:" in ln),
            "",
        )
        reachable = "Avail" in output or "NonQual" in output
        if "Avail" in output:
            detail = contact_line or "Avail"
        elif "NonQual" in output:
            detail = (contact_line or "NonQual") + "  (qualify disabled — static contact)"
        else:
            detail = contact_line or "Unreachable — check HT813 SIP server IP setting"
        status = PASS if reachable else WARN
        _row("HT813 SIP contact state", status, detail)
        return reachable
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        _row("HT813 SIP contact state", FAIL, str(exc))
        return False


def check_agi_port(host: str = "127.0.0.1", port: int = 4573) -> bool:
    """TCP-connect to the FastAGI server port."""
    try:
        with socket.create_connection((host, port), timeout=3):
            _row(f"FastAGI TCP port {port} reachable", PASS, f"{host}:{port} open")
            return True
    except (ConnectionRefusedError, OSError) as exc:
        _row(f"FastAGI TCP port {port} reachable", WARN,
             f"not listening — start teleblock-agi service ({exc})")
        return False


def check_db(db_path: str = "/var/lib/teleblock/calls.db") -> bool:
    """Verify the SQLite DB exists and has the expected schema."""
    path = Path(db_path)
    if not path.exists():
        _row("SQLite DB exists", FAIL, db_path)
        return False
    try:
        with sqlite3.connect(db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='calls'")
            row = cur.fetchone()
            if not row:
                _row("SQLite schema (calls table)", FAIL, "table missing — run db/schema.sql")
                return False
            cur.execute("SELECT COUNT(*) FROM calls")
            total: int = cur.fetchone()[0]
            _row("SQLite DB and schema", PASS, f"{db_path}  |  {total} call record(s)")
            return True
    except sqlite3.Error as exc:
        _row("SQLite DB and schema", FAIL, str(exc))
        return False


def show_call_log(db_path: str = "/var/lib/teleblock/calls.db") -> None:
    """Print a breakdown of call results from the DB."""
    path = Path(db_path)
    if not path.exists():
        return
    try:
        with sqlite3.connect(db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT result, COUNT(*) AS cnt FROM calls GROUP BY result ORDER BY cnt DESC"
            )
            rows: list[Any] = cur.fetchall()
            if not rows:
                print("\n  Call log: (empty — no calls recorded yet)")
                return
            print(f"\n  {'Result':<12} {'Count':>6}")
            print("  " + "─" * 20)
            for result, cnt in rows:
                print(f"  {result:<12} {cnt:>6}")
    except sqlite3.Error:
        pass


def check_house_phone_endpoint() -> bool:
    """Check that house-phone PJSIP endpoint is loaded (FXS / analogue phone side)."""
    try:
        result = subprocess.run(
            ["sudo", "docker", "exec", "asterisk",
             "asterisk", "-rx", "pjsip show endpoints"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        output = result.stdout
        has_endpoint = "house-phone" in output
        detail_line = next(
            (ln.strip() for ln in output.splitlines() if "house-phone" in ln), ""
        )
        _row("PJSIP endpoint house-phone loaded", PASS if has_endpoint else WARN,
             detail_line or "endpoint not found — check pjsip.conf [house-phone]")
        return has_endpoint
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        _row("PJSIP endpoint house-phone loaded", FAIL, str(exc))
        return False


def check_dialplan(skip_docker: bool) -> None:
    """Show loaded dialplan contexts and assert required ones are present."""
    if skip_docker:
        _row("Dialplan contexts", SKIP, "--no-docker flag set")
        return
    try:
        result = subprocess.run(
            ["sudo", "docker", "exec", "asterisk",
             "asterisk", "-rx", "dialplan show"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        contexts = [ln.strip() for ln in result.stdout.splitlines()
                    if ln.startswith("[ Context")]
        has_pstn = any("from-pstn" in c for c in contexts)
        has_internal = any("from-internal" in c for c in contexts)
        has_test = any("from-pstn-test" in c for c in contexts)
        detail = ", ".join(
            c.replace("[ Context '", "").replace("'", "").split(" ")[0]
            for c in contexts
        )
        _row("Dialplan [from-pstn] loaded", PASS if has_pstn else WARN,
             detail if detail else "no contexts found")
        _row("Dialplan [from-internal] loaded", PASS if has_internal else WARN,
             "(outbound — house phone → PSTN)" if has_internal
             else "MISSING — house phone cannot dial out")
        _row("Dialplan [from-pstn-test] loaded", PASS if has_test else WARN,
             "(passthrough test context)")
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        _row("Dialplan contexts", FAIL, str(exc))


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Teleblock stack health check")
    parser.add_argument(
        "--no-docker", action="store_true",
        help="Skip Docker/Asterisk checks (use if running bare-metal Asterisk)"
    )
    args = parser.parse_args()

    print(f"\n{BOLD}Teleblock Stack Verification{RESET}")
    print("=" * (ROW_WIDTH + 10))

    results: list[bool] = []

    if not args.no_docker:
        print(f"\n{BOLD}[1] Asterisk (Docker){RESET}")
        docker_up = check_docker_running()
        results.append(docker_up)
        if docker_up:
            results.append(check_asterisk_core())
            results.append(check_pjsip_endpoints())
            results.append(check_house_phone_endpoint())
            results.append(check_pjsip_contact())
            check_dialplan(skip_docker=False)
        else:
            print(f"      {YELLOW}Skipping Asterisk checks — container not running{RESET}")
    else:
        print(f"\n{BOLD}[1] Asterisk (Docker){RESET}")
        _row("Docker container checks", SKIP, "--no-docker")

    print(f"\n{BOLD}[2] FastAGI Server (host){RESET}")
    results.append(check_agi_port())

    print(f"\n{BOLD}[3] Database{RESET}")
    results.append(check_db())

    show_call_log()

    passed = sum(1 for r in results if r)
    total = len(results)
    colour = GREEN if passed == total else (YELLOW if passed >= total // 2 else RED)
    print(f"\n{'=' * (ROW_WIDTH + 10)}")
    print(f"  Result: {colour}{BOLD}{passed}/{total} checks passed{RESET}\n")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
