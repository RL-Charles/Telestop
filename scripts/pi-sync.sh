#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=pi-env.sh
source "$script_dir/pi-env.sh"

remote_host="$PI_HOST"
remote_path="${PI_SOURCE_DIR%/}/"
mode="${1:---dry-run}"

case "$mode" in
  --dry-run)
    dry_run=(--dry-run)
    ;;
  --apply)
    dry_run=()
    ;;
  *)
    echo "Usage: $0 [--dry-run|--apply]" >&2
    exit 2
    ;;
esac

ssh -o BatchMode=yes "$remote_host" \
  "test -d '$remote_path' && test -w '$remote_path'"

rsync -az --itemize-changes "${dry_run[@]}" \
  --exclude='.git/' \
  --exclude='.env' \
  --include='.env.example' \
  --exclude='.env.*' \
  --exclude='.telestop.local' \
  --exclude='.venv/' \
  --exclude='venv/' \
  --exclude='.pytest_cache/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='*.db' \
  --exclude='*.db-*' \
  --exclude='*.sqlite*' \
  --exclude='*.log' \
  --exclude='call_report.txt' \
  --exclude='asterisk/manager.conf' \
  --exclude='asterisk/pjsip.conf' \
  ./ "$remote_host:$remote_path"

if [[ "$mode" == "--dry-run" ]]; then
  echo "Dry run only. Re-run with --apply to synchronize these changes."
fi
