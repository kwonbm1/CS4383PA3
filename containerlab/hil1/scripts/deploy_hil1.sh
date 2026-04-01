#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

containerlab deploy -t topology.clab.yml

echo "HIL1 deployed. Verify OSPF convergence with:"
echo "  ./scripts/collect_ospf_state.sh"
