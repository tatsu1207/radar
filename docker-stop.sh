#!/usr/bin/env bash
# Stop RADAR Docker Compose services for the current user.
set -euo pipefail

USER_NAME=$(whoami)
export COMPOSE_PROJECT_NAME="radar-${USER_NAME}"

echo "Stopping RADAR (project=${COMPOSE_PROJECT_NAME})..."
docker compose down "$@"
