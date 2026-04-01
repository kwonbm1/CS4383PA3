#!/usr/bin/env bash
set -euo pipefail

LAB_NAME="${1:-pa3-hil1}"
SRC="clab-${LAB_NAME}-ingress-host"
DST_IP="${2:-192.168.20.10}"

# Install traceroute if missing (alpine package manager).
docker exec "$SRC" sh -lc "command -v traceroute >/dev/null || apk add --no-cache traceroute >/dev/null"

echo "Running traceroute from ingress host to ${DST_IP}"
docker exec "$SRC" sh -lc "traceroute -n ${DST_IP}"
