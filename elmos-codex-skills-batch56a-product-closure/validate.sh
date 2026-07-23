#!/usr/bin/env bash
set -euo pipefail
python3 "$(dirname "$0")/scripts/validate_package.py"
bash -n "$(dirname "$0")/install.sh"
bash -n "$(dirname "$0")/validate.sh"
