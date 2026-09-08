# Telestop workspace

This repository controls the Teleblock installation on the Raspberry Pi.

## Remote target

Copy `.telestop.local.example` to `.telestop.local` and set the SSH alias and
remote paths for the target device. The local file is ignored by Git. Use the
values loaded by `scripts/pi-env.sh`; never hard-code a personal username,
hostname, address, or home-directory path in tracked files.

Use `ssh -o BatchMode=yes "$PI_HOST"` for remote commands. Never request,
print, copy, or commit passwords, private keys, `.env`, call databases, caller
IDs, call reports, or logs.

## Working method

1. Treat this local checkout as the source of truth.
2. Inspect `git status` before editing and keep unrelated changes intact.
3. Run the local test suite before synchronization.
4. Preview changes with `scripts/pi-sync.sh`; apply them only with
   `scripts/pi-sync.sh --apply`.
5. Run `scripts/pi-test.sh` after synchronization.
6. Deploy deliberately with `scripts/pi-deploy.sh`; add `--build` only when
   the container image needs rebuilding.
7. Review the diff before making a focused commit.

The sync helper preserves the Pi's `.git`, `.env`, virtual environment,
caches, reports, runtime data, and credential-bearing live Asterisk files
(`manager.conf` and `pjsip.conf`). It intentionally does not use `--delete`.

The live services run from the configured `PI_APP_DIR`, separate from the
editable source checkout. Treat deployments, service restarts, reboots,
package changes, firewall changes, and edits under `/etc` or `/opt` as
consequential operations. Explain and verify them before execution.

## Verification

Run:

```bash
python -m pytest -q
scripts/pi-test.sh
scripts/pi-status.sh
```

When debugging telephony, preserve current calls and collect read-only status
and logs before reloading Asterisk or restarting either service.
