#!/usr/bin/env python3
"""
Teleblock — HT813 Endpoint Diagnostic Script.

Queries Asterisk (via docker exec) for the full PJSIP state of the ht813-fxo
endpoint, then watches for a test call and reports what Asterisk sees.

Usage:
    python3 scripts/ht813_diag.py            # snapshot + watch mode
    python3 scripts/ht813_diag.py --snapshot  # one-shot report, no call wait
"""
import argparse
import subprocess
import sys
import time
from datetime import datetime

GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
BOLD   = "\033[1m"
RESET  = "\033[0m"
DIM    = "\033[2m"


def _run(*cmd: str, timeout: int = 10) -> str:
    try:
        r = subprocess.run(list(cmd), capture_output=True, text=True, timeout=timeout)
        return (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return "[timeout]"
    except FileNotFoundError:
        return f"[command not found: {cmd[0]}]"


def _docker(*args: str) -> str:
    return _run("sudo", "docker", "exec", "asterisk", "asterisk", "-rx", " ".join(args))


def _section(title: str) -> None:
    bar = "─" * 60
    print(f"\n{CYAN}{BOLD}{bar}{RESET}")
    print(f"{CYAN}{BOLD}  {title}{RESET}")
    print(f"{CYAN}{BOLD}{bar}{RESET}")


def check_container() -> bool:
    out = _run("sudo", "docker", "ps", "--filter", "name=asterisk", "--format", "{{.Status}}")
    running = "Up" in out
    status_str = f"{GREEN}Running{RESET}" if running else f"{RED}NOT running{RESET}"
    print(f"  Asterisk container ........... {status_str}")
    if not running:
        print(f"  {YELLOW}Start with: sudo docker compose up -d{RESET}")
    return running


def check_transport() -> None:
    out = _docker("pjsip show transports")
    print(out if out else "  [no output]")


def check_endpoints() -> None:
    out = _docker("pjsip show endpoints")
    for line in out.splitlines():
        colour = ""
        if "Avail" in line or "Not in use" in line:
            colour = GREEN
        elif "Unavailable" in line or "Unreachable" in line:
            colour = RED
        elif "Contact" in line:
            colour = DIM
        print(f"  {colour}{line}{RESET}")


def check_auths() -> None:
    out = _docker("pjsip show auths")
    print(out if out else "  [no output]")


def check_channels() -> None:
    out = _docker("core show channels")
    print(out if out else "  [no output]")


def check_dialplan() -> None:
    """Print the from-pstn-test context so we can verify it loaded."""
    out = _docker("dialplan show from-pstn-test")
    print(out if out else "  [no output]")


def sip_logger_on() -> None:
    _docker("pjsip set logger on")
    print(f"  {GREEN}PJSIP SIP logger enabled → check docker logs for SIP messages{RESET}")


def watch_for_call(seconds: int = 30) -> None:
    _section(f"Watching Asterisk logs for incoming INVITE — make a PSTN call now ({seconds}s)")
    print(f"  {YELLOW}Run the call within the next {seconds} seconds…{RESET}\n")

    # Stream docker logs with a timeout; filter for relevant events
    deadline = time.time() + seconds
    cmd = ["sudo", "docker", "logs", "asterisk", "-f", "--since", "0s"]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        keywords = ("INVITE", "Executing", "PASSTHROUGH", "challenge",
                    "CHALLENGE", "from-pstn", "CHANNEL", "Hangup",
                    "ERROR", "WARNING", "Contact", "BYE", "REGISTER",
                    "pjsip", "PJSIP", "AGI", "NoOp")
        while time.time() < deadline:
            line = proc.stdout.readline()  # type: ignore[union-attr]
            if not line:
                time.sleep(0.05)
                continue
            line = line.rstrip()
            if any(kw in line for kw in keywords):
                ts = datetime.now().strftime("%H:%M:%S")
                flag = (
                    f"{RED}[ERR]{RESET}" if "ERROR" in line
                    else f"{YELLOW}[WARN]{RESET}" if "WARNING" in line
                    else f"{GREEN}[LOG]{RESET}"
                )
                print(f"  {DIM}{ts}{RESET} {flag}  {line}")
        proc.terminate()
    except KeyboardInterrupt:
        pass


def snapshot(container_ok: bool) -> None:
    if not container_ok:
        return

    _section("PJSIP Transport")
    check_transport()

    _section("PJSIP Endpoints / Contacts")
    check_endpoints()

    _section("Active Channels")
    check_channels()

    _section("Dialplan — from-pstn-test")
    check_dialplan()

    _section("SIP Logger")
    sip_logger_on()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="HT813 ↔ Asterisk diagnostic snapshot for Teleblock.",
    )
    parser.add_argument(
        "--snapshot", action="store_true",
        help="Print state snapshot only; don't wait for a test call.",
    )
    parser.add_argument(
        "--watch", type=int, default=30, metavar="SECONDS",
        help="Seconds to watch for an incoming call (default: 30).",
    )
    args = parser.parse_args()

    print(f"\n{BOLD}Teleblock — HT813 Diagnostic  {DIM}{datetime.now().isoformat(timespec='seconds')}{RESET}")
    print(f"  HT813 IP (direct eth0 link): {CYAN}192.168.42.145{RESET}")
    print(f"  Pi SIP address:              {CYAN}192.168.42.1:5060{RESET}")

    _section("Container Status")
    container_ok = check_container()

    snapshot(container_ok)

    if not args.snapshot and container_ok:
        watch_for_call(args.watch)

    print(f"\n{DIM}{'─' * 60}{RESET}\n")


if __name__ == "__main__":
    main()
