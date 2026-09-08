#!/usr/bin/env bash

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
config_file=${TELESTOP_CONFIG:-"$repo_root/.telestop.local"}

if [[ -f "$config_file" ]]; then
  # This file is local-only and must contain simple shell assignments.
  # shellcheck source=/dev/null
  source "$config_file"
fi

: "${PI_HOST:=telestop-pi}"
: "${PI_SOURCE_DIR:=/srv/telestop/source}"
: "${PI_APP_DIR:=/opt/teleblock/app}"
: "${PI_TEST_PYTHON:=$PI_SOURCE_DIR/.venv/bin/python}"

export PI_HOST PI_SOURCE_DIR PI_APP_DIR PI_TEST_PYTHON
