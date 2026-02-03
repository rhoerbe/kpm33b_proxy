#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONF="${SCRIPT_DIR}/kpm33b_broker.conf"

echo "Starting KPM33B internal broker on port 11883 ..."
exec mosquitto -c "${CONF}" -v
