#!/usr/bin/env bash
# Runs the two CAS checks that need this machine: Docker (Testcontainers + Flyway)
# and a local PostgreSQL for the migration constraint suite.
#
# One script rather than a pasted block: a multi-line paste keeps getting split at
# the && and the step silently never runs, which then looks like a pass.
#
# Safe to re-run. Nothing here writes to the repository.

set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO" || exit 1
echo "repo: $REPO"

step1=SKIPPED
step2=SKIPPED

# Run a command with a deadline, portably.  macOS has no `timeout(1)` unless
# coreutils is installed, and the one command here that must not hang forever is
# the Docker probe: with Docker Desktop stopped -- or with a proxy in front of
# the socket -- `docker info` does not fail, it waits.  A script whose first
# action is a silent unbounded wait reads as "stuck" with nothing to act on.
run_with_deadline() {
    local seconds="$1"; shift
    "$@" >/dev/null 2>&1 &
    local pid=$!
    local waited=0
    while kill -0 "$pid" 2>/dev/null; do
        if [ "$waited" -ge "$seconds" ]; then
            kill -9 "$pid" 2>/dev/null
            wait "$pid" 2>/dev/null
            return 124
        fi
        sleep 1
        waited=$((waited + 1))
    done
    wait "$pid"
}

echo
echo "=== 1/2  Testcontainers + Flyway (needs Docker) ==============================="
if [ -n "${ELMOS_SKIP_DOCKER:-}" ]; then
    echo "ELMOS_SKIP_DOCKER is set -- skipping straight to step 2."
elif ! command -v docker >/dev/null 2>&1; then
    echo "No docker on PATH. Install Docker Desktop, or run with ELMOS_SKIP_DOCKER=1."
else
    echo "checking whether the Docker daemon answers (20s limit)..."
    run_with_deadline 20 docker info
    case $? in
        0)
            echo "pulling postgres:17.5-alpine (first time only, be patient -- do not Ctrl-C)..."
            docker pull postgres:17.5-alpine || echo "pull failed; the test may still use a cached image"
            if mvn -f pom.xml -pl modules/persistence -am test; then step1=PASSED; else step1=FAILED; fi
            ;;
        124)
            echo "The Docker daemon did not answer within 20s."
            echo "Usually that means Docker Desktop is not running, or a proxy (Clash and"
            echo "friends) is intercepting the socket. Start Docker Desktop, wait for the"
            echo "whale to stop animating, and re-run."
            echo "To do step 2 alone in the meantime:  ELMOS_SKIP_DOCKER=1 $0"
            ;;
        *)
            echo "Docker is installed but not running. Start Docker Desktop and re-run,"
            echo "or run step 2 alone with:  ELMOS_SKIP_DOCKER=1 $0"
            ;;
    esac
fi

echo
echo "=== 2/2  V65 constraints against a real PostgreSQL (no Docker) ================"

# `pip` and `python3` are not required to be the same interpreter, and on a
# Homebrew Mac they routinely are not: `pip` can belong to python@3.11 while
# `python3` resolves to python@3.14. `pip install X && python3 script.py` then
# prints a successful install followed by ModuleNotFoundError, and re-running
# the install fixes nothing -- it keeps installing into the interpreter that is
# not the one running the script. So: pick ONE interpreter, install with
# `$PY -m pip`, run with the same `$PY`.
#
# Set ELMOS_PYTHON to override the choice.
has_modules() { "$1" -c 'import pgserver, psycopg' >/dev/null 2>&1; }

INTERPRETER=""
if [ -n "${ELMOS_PYTHON:-}" ]; then
    INTERPRETER="$ELMOS_PYTHON"
    echo "using ELMOS_PYTHON=$INTERPRETER"
else
    # An interpreter that already has both wins outright: no install, and no
    # chance of a wheel resolving differently than it did last time.
    for candidate in python3 python3.13 python3.12 python3.11; do
        command -v "$candidate" >/dev/null 2>&1 || continue
        if has_modules "$candidate"; then
            INTERPRETER="$candidate"
            echo "$candidate already has pgserver + psycopg"
            break
        fi
    done
fi

if [ -z "$INTERPRETER" ]; then
    # Nobody has them. Install into the first interpreter that accepts the
    # wheels. pgserver ships a bundled PostgreSQL binary and does not publish a
    # wheel for every Python version, so "python3 is the newest" is not the
    # same as "python3 works".
    for candidate in python3 python3.13 python3.12 python3.11; do
        command -v "$candidate" >/dev/null 2>&1 || continue
        echo "installing pgserver + psycopg[binary] into $candidate ..."
        if "$candidate" -m pip install --quiet pgserver 'psycopg[binary]' && has_modules "$candidate"; then
            INTERPRETER="$candidate"
            break
        fi
        echo "  $candidate could not provide them; trying the next interpreter"
    done
fi

if [ -z "$INTERPRETER" ]; then
    echo "No Python on this machine could install pgserver + psycopg[binary]."
    echo "Install them yourself and re-run with, e.g.:"
    echo "    ELMOS_PYTHON=python3.12 $0"
else
    echo "constraint suite interpreter: $("$INTERPRETER" -c 'import sys; print(sys.executable, sys.version.split()[0])')"
    if "$INTERPRETER" scripts/cas/verify_v65_migration.py; then step2=PASSED; else step2=FAILED; fi
fi

echo
echo "=== summary ==================================================================="
printf '  %-46s %s\n' "modules/persistence test (Flyway + Testcontainers)" "$step1"
printf '  %-46s %s\n' "verify_v65_migration.py (45 constraint checks)" "$step2"
echo
echo "surefire reports written this run:"
find modules/persistence/target/surefire-reports -name 'TEST-*Cas*.xml' -newermt '-30 minutes' \
    -exec sh -c 'printf "  %s\n" "$(basename "$1")"; grep -o "tests=\"[0-9]*\" errors=\"[0-9]*\" skipped=\"[0-9]*\" failures=\"[0-9]*\"" "$1" | head -1 | sed "s/^/      /"' _ {} \; 2>/dev/null \
    || echo "  (none — the Docker half did not run)"
