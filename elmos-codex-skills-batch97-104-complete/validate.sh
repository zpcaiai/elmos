#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_RUNNER=(python3)

if ! python3 -c 'from importlib.metadata import version; assert tuple(map(int, version("jsonschema").split(".")[:2])) >= (4, 23)' >/dev/null 2>&1; then
  UV_BIN="${UV_BIN:-$(command -v uv || true)}"
  if [[ -z "$UV_BIN" ]]; then
    echo "jsonschema is required; install it or provide uv through UV_BIN" >&2
    exit 2
  fi
  PYTHON_RUNNER=("$UV_BIN" run --quiet --with 'jsonschema==4.25.1' python)
fi

"${PYTHON_RUNNER[@]}" "$ROOT/scripts/validate_package.py" "$ROOT" "$@"
"${PYTHON_RUNNER[@]}" -m unittest discover -s "$ROOT/tests" -p 'test_*.py'
bash -n "$ROOT/validate.sh" "$ROOT/install.sh"
