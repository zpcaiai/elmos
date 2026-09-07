#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$ROOT/tools/validate_package.py" --root "$ROOT"
python3 -m unittest discover -s "$ROOT/tests" -p 'test_*.py' -v
python3 "$ROOT/tools/quote_reference.py" "$ROOT/examples/quote-calculator-input.example.json" --output /tmp/elmos-billing-quote-reference.json
printf 'Reference quote generated: %s\n' /tmp/elmos-billing-quote-reference.json
