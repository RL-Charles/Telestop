#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=pi-env.sh
source "$script_dir/pi-env.sh"

printf -v remote_command 'cd %q && %q -m pytest -q' \
  "$PI_SOURCE_DIR" "$PI_TEST_PYTHON"
exec ssh -o BatchMode=yes "$PI_HOST" "$remote_command"
