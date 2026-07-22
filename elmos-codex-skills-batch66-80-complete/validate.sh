#!/usr/bin/env bash
set -euo pipefail
R="$(cd "$(dirname "${BASH_SOURCE[0]}")"&&pwd)";python3 "$R/scripts/validate_package.py";python3 -m unittest discover -s "$R/tests" -p 'test_*.py';bash -n "$R/install.sh";bash -n "$R/validate.sh"
