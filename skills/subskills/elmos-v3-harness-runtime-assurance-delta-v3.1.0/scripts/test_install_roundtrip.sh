#!/usr/bin/env bash
set -euo pipefail
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_SOURCE="${1:?usage: test_install_roundtrip.sh /path/to/extracted-v3.0.0}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cp -a "$BASE_SOURCE" "$TMP/base"
python3 - "$TMP/base" > "$TMP/before.json" <<'PY'
import hashlib,json,sys
from pathlib import Path
r=Path(sys.argv[1]); print(json.dumps({str(p.relative_to(r)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(r.rglob('*')) if p.is_file() and '__pycache__' not in p.parts},sort_keys=True))
PY
"$SOURCE_DIR/scripts/install.sh" "$TMP/base"
PYTHONPATH="$TMP/base/reference-implementation/src" \
  python3 -m unittest discover -s "$TMP/base/reference-implementation/tests" -v >/dev/null
"$SOURCE_DIR/scripts/uninstall.sh" "$TMP/base"
python3 - "$TMP/base" > "$TMP/after.json" <<'PY'
import hashlib,json,sys
from pathlib import Path
r=Path(sys.argv[1]); print(json.dumps({str(p.relative_to(r)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(r.rglob('*')) if p.is_file() and '__pycache__' not in p.parts},sort_keys=True))
PY
cmp "$TMP/before.json" "$TMP/after.json"
echo "install/uninstall exact roundtrip PASS"
