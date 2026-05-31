#!/usr/bin/env bash
# Start RADAR via Docker Compose with UID-based isolation (multi-user safe).
# Each user gets unique ports, container names, and volumes.
set -euo pipefail

UID_NUM=$(id -u)
USER_NAME=$(whoami)
PROJECT_NAME="radar-${USER_NAME}"

PORT_FRONTEND=$((7200 + UID_NUM))
PORT_BACKEND=$((7210 + UID_NUM))
PORT_PG=$((7220 + UID_NUM))
PORT_REDIS=$((7230 + UID_NUM))

cat > .env <<EOF
COMPOSE_PROJECT_NAME=${PROJECT_NAME}
PORT_FRONTEND=${PORT_FRONTEND}
PORT_BACKEND=${PORT_BACKEND}
PORT_PG=${PORT_PG}
PORT_REDIS=${PORT_REDIS}
EOF

echo "Starting RADAR as ${USER_NAME} (UID=${UID_NUM}, project=${PROJECT_NAME})..."
echo "  Frontend:   http://localhost:${PORT_FRONTEND}"
echo "  Backend:    http://localhost:${PORT_BACKEND}"
echo "  PostgreSQL: localhost:${PORT_PG}"
echo "  Redis:      localhost:${PORT_REDIS}"

docker compose up -d "$@"
