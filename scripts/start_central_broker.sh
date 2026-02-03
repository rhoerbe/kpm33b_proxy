#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONF="${SCRIPT_DIR}/central_broker.conf"

mkdir -p /tmp/mosquitto_central

echo "Starting mock central broker on port 1884 ..."
exec mosquitto -c "${CONF}" -v
