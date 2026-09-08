---
applyTo: "**/{agi,asterisk,dialplan,scripts}/**"
description: "Telephony, Asterisk, DTMF, and SIP conventions for the Teleblock project. Use when writing AGI scripts, dialplan, or SIP config."
---

# Telephony Standards — Teleblock

## Grandstream HT813 FXO Integration
- The HT813 FXO port registers as a SIP peer named `ht813-fxo` in Asterisk
- Inbound PSTN calls arrive on context `[from-pstn]` in `extensions.conf`
- One concurrent call maximum — dialplan must enforce this with a semaphore or `GROUP()` check
- HT813 sends RFC 2833 DTMF events; Asterisk must be configured with `dtmfmode=rfc2833`
- Audio path: G.711 u-law (PCMU) only — strip all other codecs in `sip.conf`/`pjsip.conf`

## Asterisk Dialplan Conventions (`extensions.conf`)
```ini
; Inbound call entry point
[from-pstn]
exten => s,1,Answer()
 same => n,AGI(agi://127.0.0.1:4573/challenge)
 same => n,GotoIf($["${CHALLENGE_RESULT}" = "PASS"]?allow,1:block,1)

[allow]
exten => 1,1,Dial(SIP/internal,30)

[block]
exten => 1,1,Playback(blocked-message)
 same => n,Hangup()
```
- Use `same => n` continuation for all subsequent steps in an extension
- Set `CHANNEL(language)=en` early so audio prompts use correct locale
- Always `Answer()` the call before playing audio (otherwise audio may not reach the PSTN side)

## FastAGI Scripts
- AGI server listens on `127.0.0.1:4573` (loopback only, never bind to `0.0.0.0`)
- AGI protocol I/O uses line-buffered stdin/stdout — always flush after every write
- Read AGI environment variables from the initial handshake block before issuing any commands
- Template for a new AGI handler:
```python
async def handle(agi: AGIChannel) -> None:
    await agi.answer()
    digit = await agi.wait_for_digit(timeout_ms=5000)
    if digit not in VALID_DTMF:
        await agi.set_variable("CHALLENGE_RESULT", "FAIL")
    else:
        await agi.set_variable("CHALLENGE_RESULT", "PASS")
    # Do NOT hangup here — let the dialplan decide
```

## DTMF Handling
- Valid DTMF digits: `0-9`, `*`, `#`, `A-D`
- Always define a **timeout** when waiting for DTMF — never block indefinitely
- For multi-digit sequences, collect with a loop and validate the full sequence atomically
- Log DTMF responses as `digit_count` only (not the actual digits) to protect PIN privacy
- Challenge strategy: caller must press a single key (e.g., `1`) within 8 seconds; robodialers cannot comply

## SIP Configuration (`pjsip.conf` preferred over legacy `sip.conf`)
```ini
[ht813-fxo]
type=endpoint
context=from-pstn
disallow=all
allow=ulaw
dtmf_mode=rfc2833
from_user=ht813-fxo
auth=ht813-fxo-auth
aors=ht813-fxo-aor
```
- Set `nat=force_rport,comedia` if Pi and HT813 are behind NAT
- Keep SIP registration credentials in `.env`, loaded at startup via `asterisk.conf` `#exec`

## Call Logging
- Log every inbound call to SQLite: timestamp, plain-text CID, call result (PASS/BLOCK/TIMEOUT), DTMF digit count
- Store CID as plain text — this is a single-owner DIY device; hashing is explicitly not required
- Retention: auto-purge records older than 90 days via a daily cron job

## Audio Prompts
- Store `.wav` files in `/var/lib/asterisk/sounds/teleblock/`
- Format: 8000 Hz, 16-bit, mono, PCM WAV (use `sox input.wav -r 8000 -c 1 -b 16 output.wav` to convert)
- Prompt script: `"To complete your call, press 1 now."`
- Keep prompts under 6 seconds to avoid exceeding typical SIP session setup timers

## Blocklist
- Maintained in `data/blocklist.txt` — one pattern per line (exact number or regex)
- `scripts/blocklist.py` provides `add`, `remove`, `check` CLI subcommands
- Asterisk reads blocklist at dialplan load via `func_odbc` or a Python `#exec` — regenerate on change
