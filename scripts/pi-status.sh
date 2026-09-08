#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=pi-env.sh
source "$script_dir/pi-env.sh"

printf -v source_dir '%q' "$PI_SOURCE_DIR"
exec ssh -o BatchMode=yes "$PI_HOST" "
  echo \"Host: \$(hostname) (\$(uname -m))\"
  echo \"Uptime: \$(uptime -p)\"
  echo \"Repository:\"
  git -C $source_dir status --short --branch
  echo \"Services:\"
  systemctl is-enabled teleblock-agi.service docker-asterisk.service
  systemctl is-active teleblock-agi.service docker-asterisk.service
  echo \"Container:\"
  sudo -n docker ps --filter name=^/asterisk$ --format \
    'table {{.Names}}\\t{{.Status}}\\t{{.Image}}'
  echo \"SIP contacts:\"
  sudo -n docker exec asterisk asterisk -rx 'pjsip show contacts' | \
    sed -n '/Contact:/{p;}'
  echo \"FastAGI listener:\"
  ss -ltn | grep -F '127.0.0.1:4573'
"
