#!/usr/bin/env bash
# PA2 Milestone 1: Build and push images to private registry.
# Usage: ./scripts/build-and-push.sh [REGISTRY] [TEAM]
# Example: ./scripts/build-and-push.sh 192.168.1.129:5000 team10
# Run from repo root. Requires docker login to registry.

set -e
REGISTRY="${1:-192.168.1.88:5000}"
TEAM="${2:-team1}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

services=(ordering-service inventory-service pricing-service analytics-service robot-service client)
for svc in "${services[@]}"; do
  case "$svc" in
    ordering-service)  dockerfile=ordering_service/Dockerfile ;;
    inventory-service) dockerfile=inventory_service/Dockerfile ;;
    pricing-service)   dockerfile=pricing_service/Dockerfile ;;
    analytics-service)  dockerfile=analytics_service/Dockerfile ;;
    robot-service)     dockerfile=robot_service/Dockerfile ;;
    client)            dockerfile=client/Dockerfile ;;
    *) echo "Unknown service $svc"; exit 1 ;;
  esac
  tag="${REGISTRY}/${TEAM}/${svc}:latest"
  echo "Building $tag ..."
  docker build -f "$dockerfile" . -t "$tag"
  echo "Pushing $tag ..."
  docker push "$tag"
done
echo "Done. Update k8s/*.yaml image fields to ${REGISTRY}/${TEAM}/<service>:latest if different."
