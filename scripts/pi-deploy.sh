#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=pi-env.sh
source "$script_dir/pi-env.sh"

build=false
case "${1:-}" in
  "") ;;
  --build) build=true ;;
  *)
    echo "Usage: $0 [--build]" >&2
    exit 2
    ;;
esac

"$script_dir/pi-sync.sh" --apply
"$script_dir/pi-test.sh"

ssh -o BatchMode=yes "$PI_HOST" bash -s -- \
  "$PI_SOURCE_DIR" "$PI_APP_DIR" "$build" <<'REMOTE'
set -euo pipefail

source_dir=$1
app_dir=$2
build=$3

sudo -n install -d -m 0755 "$app_dir"
sudo -n rsync -a \
  --exclude='.git/' \
  --exclude='.env' \
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
  "$source_dir/" "$app_dir/"

sudo -n chmod 0640 "$app_dir/.env"
sudo -n install -m 0644 \
  "$app_dir/systemd/docker-asterisk.service" \
  /etc/systemd/system/docker-asterisk.service
sudo -n install -m 0644 \
  "$app_dir/systemd/teleblock-agi.service" \
  /etc/systemd/system/teleblock-agi.service
sudo -n systemctl daemon-reload

if [[ "$build" == true ]]; then
  sudo -n docker compose --project-directory "$app_dir" build
fi

sudo -n systemctl restart teleblock-agi.service docker-asterisk.service
sudo -n systemctl --no-pager --full status \
  teleblock-agi.service docker-asterisk.service
REMOTE
