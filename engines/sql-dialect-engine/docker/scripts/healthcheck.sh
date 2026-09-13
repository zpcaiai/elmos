#!/usr/bin/env bash
set -euo pipefail

# Health check script for Dockerized databases and CDC services
echo "======================================================"
echo "ELMOS CDC Cluster Health Check"
echo "======================================================"

TIMEOUT=60
START_TIME=$(date +%s)

check_port() {
    local host="$1"
    local port="$2"
    local service_name="$3"
    local elapsed=0

    echo -n "Checking ${service_name} (${host}:${port})... "
    while ! nc -z -w 2 "${host}" "${port}" 2>/dev/null; do
        sleep 2
        elapsed=$(( $(date +%s) - START_TIME ))
        if [ "$elapsed" -ge "$TIMEOUT" ]; then
            echo "FAILED (timeout after ${TIMEOUT}s)"
            return 1
        fi
        echo -n "."
    done
    echo " OK (${elapsed}s)"
    return 0
}

ERRORS=0

# Check Postgres source
check_port "127.0.0.1" "55432" "PostgreSQL 16 Source" || ERRORS=$((ERRORS + 1))

# Check MySQL source
check_port "127.0.0.1" "33306" "MySQL 8.0 Source" || ERRORS=$((ERRORS + 1))

# Check openGauss target
check_port "127.0.0.1" "54321" "openGauss 3.0 Target" || ERRORS=$((ERRORS + 1))

# Check DM8 target
check_port "127.0.0.1" "5236" "DM8 Target (Dameng 8)" || ERRORS=$((ERRORS + 1))

echo "======================================================"
if [ "$ERRORS" -eq 0 ]; then
    echo "All database instances are reachable and healthy!"
    exit 0
else
    echo "Health check failed with ${ERRORS} unreachable service(s)."
    exit 1
fi
