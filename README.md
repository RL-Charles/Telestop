# Telestop

Automated DTMF-based telemarketer blocking for a PSTN landline, running on a **Raspberry Pi 5** connected to a **Grandstream HT813** FXO ATA.

> **Status:** Operational. Challenge prompt plays, DTMF digit collection works,
> house phone rings on pass, robocallers are blocked and silently disconnected. Call history persists
> through reboots and crashes. See [Known Issues & Fixes](#known-issues--fixes) for the critical
> `ast_waitfordigit_full` fix that was required to make DTMF collection reliable.

---

## How It Works

1. A PSTN call arrives on the HT813 FXO port and is forwarded as a SIP INVITE to Asterisk on the Pi.
2. Asterisk answers the call and checks whether the caller is already trusted (via FastAGI DB lookup).
3. If trusted — skip the challenge and connect immediately.
4. If unknown — Asterisk plays the challenge prompt: *"Press 1 to complete your call."*
5. The caller presses `1` within 8 seconds → call is connected to the house phone (which rings).
6. No DTMF, wrong digit, or robocaller that can't comply → call is blocked and disconnected.
7. Every call event (PASS / FAIL / TIMEOUT) is logged to a local SQLite database.
8. On first PASS, the caller's number is added to the trusted list and skips the challenge on future calls.

### Call Flow Diagram

```
Inbound PSTN call
        │
        ▼
  AGI: check_trusted ──► IS_TRUSTED=1 ──► Set(PASS) → AGI: log_result → [allow] → house phone rings
        │
        │ IS_TRUSTED=0
        ▼
  Read(DTMF_DIGIT, teleblock/challenge, 1,,1,8)
  [plays prompt + collects digit in pure dialplan]
        │
        ├─ digit = "1" ──► Set(PASS)    → AGI: log_result → [allow] → house phone rings
        ├─ digit = ""  ──► Set(TIMEOUT) → AGI: log_result → [block] → disconnected
        └─ digit = ?   ──► Set(FAIL)    → AGI: log_result → [block] → disconnected
```

---

## Requirements

| Component | Details |
|-----------|---------|
| Raspberry Pi 5 | Raspberry Pi OS Bookworm 64-bit (headless) |
| Grandstream HT813 | FXO port configured as SIP peer to Pi |
| Asterisk 20 LTS | Runs in Docker (`docker-asterisk.service`) |
| Python 3.11+ | FastAGI server in virtualenv (`teleblock-agi.service`) |
| SQLite 3 | Call log at `/var/lib/teleblock/calls.db` (WAL mode) |

---

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/RL-Charles/Telestop.git
cd Telestop

# 2. Configure environment
cp .env.example .env
# Edit .env — set SIP credentials, AGI port, DB path, challenge digit

# 3. Start everything
sudo systemctl start docker-asterisk.service
sudo systemctl start teleblock-agi.service

# 4. Verify endpoints registered
sudo docker exec asterisk asterisk -rx "pjsip show endpoints"

# 5. Run tests
pytest tests/ -v
```

---

## Project Structure

```
teleblock/
├── .github/
│   ├── copilot-instructions.md         # Workspace-wide Copilot instructions
│   └── instructions/
│       ├── python.instructions.md      # Python conventions
│       ├── telephony.instructions.md   # Asterisk / DTMF / SIP
│       └── raspberry-pi.instructions.md
├── agi/
│   ├── server.py       # FastAGI TCP server (asyncio)
│   ├── challenge.py    # check_trusted + log_result AGI modes
│   └── db.py           # SQLite helpers (WAL, trusted callers, call log)
├── asterisk/
│   ├── extensions.conf # Dialplan — Read() DTMF collection, routing
│   └── pjsip.conf      # SIP trunk config for HT813 FXO + FXS ports
├── db/
│   └── schema.sql      # SQLite schema (calls + trusted_callers tables)
├── scripts/
│   ├── call_report.sh  # Formatted call report (see Reporting section)
│   ├── ht813_diag.py   # HT813 diagnostics
│   └── verify.py       # Stack verification
├── systemd/
│   ├── docker-asterisk.service   # Asterisk Docker container
│   └── teleblock-agi.service     # Python FastAGI server
├── tests/
├── .env.example
├── requirements.txt
└── README.md
```

---

## Configuration (`.env`)

See `.env.example` for all options. Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `AGI_HOST` | `127.0.0.1` | FastAGI listen address |
| `AGI_PORT` | `4573` | FastAGI listen port |
| `DB_PATH` | `/var/lib/teleblock/calls.db` | SQLite database path |
| `CHALLENGE_DIGIT` | `1` | DTMF digit the caller must press |
| `CHALLENGE_TIMEOUT_MS` | `8000` | Milliseconds to wait for digit |
| `LOG_LEVEL` | `INFO` | Python log level (`DEBUG` for full AGI trace) |

---

## Services & Startup

Two systemd services must be running for calls to work:

```bash
# Start
sudo systemctl start docker-asterisk.service
sudo systemctl start teleblock-agi.service

# Enable on boot
sudo systemctl enable docker-asterisk.service
sudo systemctl enable teleblock-agi.service

# Status check
sudo systemctl status docker-asterisk.service teleblock-agi.service --no-pager
```

### Deploying from a workstation

Copy `.telestop.local.example` to `.telestop.local` and set the SSH alias and
remote paths for your Pi. The local file is ignored by Git and must not contain
anything you intend to publish.

```bash
# Preview and synchronize source to the Pi
scripts/pi-sync.sh
scripts/pi-sync.sh --apply

# Test on the Pi, deploy, and restart the services
scripts/pi-test.sh
scripts/pi-deploy.sh

# Rebuild the image only when Docker inputs have changed
scripts/pi-deploy.sh --build
```

The boot service uses the already-built image, so telephony startup does not
depend on Internet access, registry availability, or a synchronized clock.

---

## Monitoring Live Calls

Open three terminals before making a test call:

**Terminal 1 — Asterisk dialplan trace:**
```bash
sudo docker exec -it asterisk asterisk -rvvv
```

**Terminal 2 — FastAGI live log:**
```bash
sudo journalctl -u teleblock-agi -f
```

**Terminal 3 — Database live tail:**
```bash
watch -n 2 "sudo sqlite3 /var/lib/teleblock/calls.db \
  'SELECT id, ts, cid, result FROM calls ORDER BY id DESC LIMIT 10;'"
```

### What a healthy call looks like in the Asterisk console

```
Executing [s@from-pstn:6]  AGI(agi://127.0.0.1:4573,check_trusted)
Executing [s@from-pstn:7]  GotoIf IS_TRUSTED
Executing [s@from-pstn:8]  Read(DTMF_DIGIT,teleblock/challenge,1,,1,8)
  -- <channel> Playing 'teleblock/challenge.ulaw'
  -- User entered '1'
Executing [s@from-pstn:9]  GotoIf DTMF_DIGIT = 1
Executing [s@from-pstn:10] Set(CHALLENGE_RESULT=PASS)
Executing [s@from-pstn:11] AGI(agi://127.0.0.1:4573,log_result)
Executing [s@from-pstn:12] Goto(allow,s,1)
Executing [s@allow:2]      Dial(PJSIP/house-phone,30,gr)   ← house phone rings
```

---

## Reporting

`scripts/call_report.sh` provides a formatted summary of all call data.

```bash
# Full report (summary + blocked + trusted + daily + all numbers)
./scripts/call_report.sh

# Today's calls only
./scripts/call_report.sh --today

# Blocked numbers only
./scripts/call_report.sh --blocked
```

### Example summary output

```
  Total calls logged:           42
  Calls passed (connected):     12
  Calls blocked (total):        30
    ↳ Timed out (no digit):    29
    ↳ Failed (wrong digit):     1
  Unique numbers blocked:       24
  Trusted callers on file:       8

  First call recorded:  2026-01-01 09:00:00
  Most recent call:     2026-01-07 18:30:00
```

### Useful ad-hoc queries

```bash
# All blocked numbers with counts
sudo sqlite3 /var/lib/teleblock/calls.db "
SELECT cid, COUNT(*) as blocked, MIN(ts) as first_seen, MAX(ts) as last_seen
FROM calls WHERE result IN ('TIMEOUT','FAIL')
GROUP BY cid ORDER BY blocked DESC;"

# Calls by day (last 30 days)
sudo sqlite3 /var/lib/teleblock/calls.db "
SELECT DATE(ts) as day, COUNT(*) as total,
  SUM(result='PASS') as passed, SUM(result='TIMEOUT') as timed_out
FROM calls GROUP BY day ORDER BY day DESC LIMIT 30;"

# Check / remove a number from trusted callers
sudo sqlite3 /var/lib/teleblock/calls.db "SELECT * FROM trusted_callers WHERE cid = '5551234567';"
sudo sqlite3 /var/lib/teleblock/calls.db "DELETE FROM trusted_callers WHERE cid = '5551234567';"
```

---

## Persistent Storage

Call data is stored on the **host filesystem** (`/var/lib/teleblock/calls.db`), not inside the Docker
container. WAL journal mode is enabled on every connection, protecting against corruption on unclean
shutdown. The Docker volume mount in `docker-compose.yml` is:

```yaml
- /var/lib/teleblock:/var/lib/teleblock
```

Verify persistence at any time:
```bash
sudo sqlite3 /var/lib/teleblock/calls.db "PRAGMA journal_mode; PRAGMA integrity_check;"
# Expected: wal / ok
```

---

## Known Issues & Fixes

The September 2026 outage, its evidence timeline, and the hardening work are
documented in [the incident report](docs/incident-2026-09-03.md).

### `ast_waitfordigit_full` FD Race — DTMF always TIMEOUT (fixed 29 April 2026)

**Symptom:** Every inbound call resulted in `CHALLENGE_RESULT=TIMEOUT` in ~12ms regardless of what
digit was pressed. The house phone never rang. The challenge prompt either didn't play or was cut off.

**Root cause:** The HT813 starts streaming RTP audio packets immediately after Asterisk answers the
call. Asterisk's internal `ast_waitfordigit_full` function — used by `STREAM FILE`, `WAIT FOR DIGIT`,
and `GET VARIABLE` in AGI — polls the channel audio file descriptor for DTMF and hangup events. The
incoming RTP packets made that FD immediately readable. `ast_waitfordigit_full` misread this as a
signal and returned in ~12ms, causing every AGI command that touched the channel to fail instantly.

**Fix:** All DTMF collection and call routing was moved out of the AGI entirely and into the Asterisk
dialplan using `Read()`. The `Read()` application plays the challenge prompt and collects a digit in
one step using a code path that handles incoming RTP correctly. The AGI is now called twice per call
but neither invocation polls the channel FD:

- `AGI(agi://127.0.0.1:4573,check_trusted)` — DB lookup only; writes `IS_TRUSTED` via `SET VARIABLE`
- `AGI(agi://127.0.0.1:4573,log_result)` — reads `CHALLENGE_RESULT` from the AGI env block, writes to SQLite

Additionally, `trust_id_inbound=yes` was added to `pjsip.conf` so Asterisk reads the real PSTN caller
ID from the HT813's P-Asserted-Identity header instead of logging the SIP username (`ht813-fxo`).

**Files changed:** `asterisk/extensions.conf`, `agi/challenge.py`, `asterisk/pjsip.conf`

---

## Security Notes

- Asterisk AMI binds to `127.0.0.1` only — never expose it externally
- SIP port 5060 is bound to `192.168.42.1` (Pi's direct-link interface to HT813) — not the WAN
- Caller ID is stored as plain text in SQLite — single-owner DIY device, no hashing required
- `.env` is excluded from version control via `.gitignore`
- The FastAGI service runs as the `asterisk` user with `NoNewPrivileges=yes` and `ProtectSystem=strict`

---

## License

MIT
