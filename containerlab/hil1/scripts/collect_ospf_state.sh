#!/usr/bin/env bash
set -euo pipefail

LAB_NAME="${1:-pa3-hil1}"
OUT_DIR="${2:-./outputs/$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$OUT_DIR"

routers=(r1 r2 r3 r4)
commands=(
  'vtysh -c "show ip route"'
  'vtysh -c "show ip ospf neighbor"'
  'vtysh -c "show ip ospf database"'
)

for r in "${routers[@]}"; do
  cname="clab-${LAB_NAME}-${r}"
  for cmd in "${commands[@]}"; do
    short=$(echo "$cmd" | tr ' ' '_' | tr -d '"')
    out_file="$OUT_DIR/${r}_${short}.txt"
    echo "Collecting ${cmd} from ${cname} -> ${out_file}"
    docker exec "$cname" sh -lc "$cmd" > "$out_file"
  done
done

echo "Saved OSPF evidence to: $OUT_DIR"
