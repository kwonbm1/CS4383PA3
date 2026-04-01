#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <router-name> <interface> [pcap-output]"
  echo "Example: $0 r2 eth3 ./outputs/r2-eth3.pcap"
  exit 1
fi

LAB_NAME="${LAB_NAME:-pa3-hil1}"
ROUTER="$1"
IFACE="$2"
OUT="${3:-./outputs/${ROUTER}-${IFACE}-$(date +%Y%m%d-%H%M%S).pcap}"
mkdir -p "$(dirname "$OUT")"

CNAME="clab-${LAB_NAME}-${ROUTER}"
echo "Capturing from ${CNAME}:${IFACE} -> ${OUT}"
docker exec "$CNAME" tcpdump -i "$IFACE" -U -w - > "$OUT"
