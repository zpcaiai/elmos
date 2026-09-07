#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

run() {
  printf '\n==> %s\n' "$1"
  shift
  "$@"
}

if command -v gradle >/dev/null 2>&1; then
  run "Gradle control-plane tests" bash -lc "cd '$ROOT/services/control-plane' && gradle test --no-daemon"
else
  echo "SKIP: Gradle not found; Docker build remains available"
fi

if command -v mvn >/dev/null 2>&1; then
  run "Maven Java engine tests" bash -lc "cd '$ROOT/engines/java-engine' && mvn test"
else
  echo "SKIP: Maven not found; Docker build remains available"
fi

if command -v python3 >/dev/null 2>&1; then
  run "Python syntax check" python3 -m compileall -q "$ROOT/services/agent-service/src"
else
  echo "SKIP: python3 not found"
fi

if command -v go >/dev/null 2>&1; then
  run "Go tests" bash -lc "cd '$ROOT/services/runner' && go test ./..."
else
  echo "SKIP: go not found"
fi

if command -v node >/dev/null 2>&1 && [[ -d "$ROOT/apps/console/node_modules" ]]; then
  run "Next.js build" bash -lc "cd '$ROOT/apps/console' && npm run build"
else
  echo "SKIP: run 'npm ci' in apps/console before the Next.js build"
fi

run "Contract JSON validation" python3 "$ROOT/scripts/validate_contracts.py"
printf '\nAll available checks passed.\n'
