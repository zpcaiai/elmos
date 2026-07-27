#!/usr/bin/env bash
set -euo pipefail
python3 scripts/validate_package.py
bash -n install.sh
bash -n validate.sh
