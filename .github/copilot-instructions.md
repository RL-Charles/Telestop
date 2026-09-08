# Teleblock — DTMF Telemarketer Blocking System

## Project Overview
This project runs on a **Raspberry Pi 5** connected to a **Grandstream HT813** ATA (FXO port).
It intercepts inbound PSTN calls, plays a challenge prompt, listens for DTMF tones, and blocks
or routes the call based on the caller's response. The goal is to automatically reject
telemarketer and robocall traffic on an old landline phone system.

## Hardware Stack
- **Compute**: Raspberry Pi 5 (Raspberry Pi OS, 64-bit)
- **ATA / FXO gateway**: Grandstream HT813 — FXO port bridges PSTN → SIP
  - SIP trunk terminates on the Pi's Asterisk instance (UDP 5060)
  - Audio codec: G.711 u-law (PCMU) preferred; G.711 a-law (PCMA) fallback
  - DTMF mode: RFC 2833 (RTP Event) — always use this, never in-band
- **Connection**: Pi and HT813 use a dedicated link — example HT813 IP: `192.168.42.145`

## Software Stack
| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ |
| PBX | Asterisk 20 (LTS) + `python-asterisk` / `pyst2` for AMI |
| AGI scripts | Python via `asterisk-agi` (FastAGI over TCP) |
| DTMF detection | Asterisk native RFC 2833 (hardware-side); `pydub` + `librosa` for offline analysis |
| Audio playback | Asterisk `Playback()` / `Background()` applications |
| Call data store | SQLite3 (local, `/var/lib/teleblock/calls.db`) |
| Configuration | `python-dotenv` + `.env` file; never hardcode credentials |
| Tests | `pytest` + `pytest-asyncio`; mock Asterisk with `unittest.mock` |
| Logging | Python `logging` module → `/var/log/teleblock/teleblock.log` |

## Architecture
```
PSTN line
  │
  ▼
Grandstream HT813 (FXO) ──SIP/RTP──► Asterisk (Pi 5)
                                           │
                              extensions.conf dialplan
                                           │
                              FastAGI TCP ─┘
                                  │
                          Python AGI scripts
                          ├── challenge.py   (play challenge, wait DTMF)
                          ├── screener.py    (allow/block decision)
                          ├── blocklist.py   (manage blocked numbers)
                          └── db.py          (SQLite call log)
```

## Key File Locations
- `asterisk/extensions.conf` — dialplan
- `asterisk/sip.conf` or `asterisk/pjsip.conf` — SIP trunk to HT813
- `agi/` — Python FastAGI scripts
- `scripts/` — standalone utilities (blocklist management, report generation)
- `tests/` — pytest suite
- `.env` — local secrets (never commit)
- `requirements.txt` — Python dependencies

## Build & Run
```bash
# Install Python deps
pip install -r requirements.txt

# Run tests
pytest tests/ -v

# Start FastAGI server (development)
python agi/server.py

# Reload Asterisk dialplan (on Pi)
sudo asterisk -rx "dialplan reload"

# Watch live call log
sudo asterisk -rvvv
```

## Coding Conventions
- Use `async`/`await` (asyncio) for all FastAGI server I/O
- All DTMF sequences must be validated before acting; never trust raw input
- Caller ID is stored in plain text in SQLite — this is a single-owner DIY device with no multi-tenant privacy concerns; do not add hashing
- All Asterisk AGI variables must be sanitised before use in shell or SQL (parameterised queries only)
- Use f-strings for formatting; avoid `%`-style string formatting in new code
- Type-annotate all public functions and class methods

## Security
- The HT813 admin panel must be password-protected and not exposed WAN-side
- Asterisk AMI binds to `127.0.0.1` only
- `.env` is in `.gitignore`; use `.env.example` for documentation
- No dynamic `eval()` or `exec()` on any data sourced from call metadata

## Common Pitfalls
- HT813 default codec order includes G.729 — disable it; Pi's Asterisk may not have a G.729 licence
- RFC 2833 DTMF requires matching `dtmfmode=rfc2833` in both `sip.conf`/`pjsip.conf` AND HT813 web UI
- Asterisk AGI reads/writes to `stdout`/`stdin` with `\n` line endings — never use `print()` without `flush=True`
- The HT813 FXO port can only handle **one concurrent call** — design the dialplan accordingly
- Raspberry Pi 5 uses PCIe-attached NVMe if present; default SD card I/O can bottleneck SQLite writes under load
