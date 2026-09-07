#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PARENT="$(dirname "$ROOT")"
NAME="$(basename "$ROOT")"
ZIP="$PARENT/$NAME.zip"
TGZ="$PARENT/$NAME.tar.gz"
SUMS="$PARENT/$NAME-SHA256SUMS.txt"

"$ROOT/verify.sh"
find "$ROOT" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$ROOT" -type f -name '*.pyc' -delete
rm -f "$ZIP" "$TGZ" "$SUMS"

ROOT="$ROOT" ZIP="$ZIP" python3 - <<'PY'
from pathlib import Path
import os
import zipfile
root = Path(os.environ["ROOT"])
out = Path(os.environ["ZIP"])
base = root.name
excluded_parts = {"__pycache__", ".elmos-backups"}
with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(part in excluded_parts for part in path.parts) or path.suffix == ".pyc":
            continue
        arc = Path(base) / path.relative_to(root)
        info = zipfile.ZipInfo(arc.as_posix(), date_time=(2026, 8, 19, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = ((0o755 if os.access(path, os.X_OK) else 0o644) & 0xFFFF) << 16
        zf.writestr(info, path.read_bytes())
PY

if tar --help 2>/dev/null | grep -q -- '--sort'; then
  tar --sort=name --mtime='2026-08-19 00:00:00Z' --owner=0 --group=0 --numeric-owner \
    --exclude='__pycache__' --exclude='*.pyc' --exclude='.elmos-backups' \
    -C "$PARENT" -czf "$TGZ" "$NAME"
else
  tar --exclude='__pycache__' --exclude='*.pyc' --exclude='.elmos-backups' \
    -C "$PARENT" -czf "$TGZ" "$NAME"
fi

python3 - "$ZIP" "$TGZ" "$SUMS" <<'PY'
from pathlib import Path
import hashlib
import sys
zip_path, tgz_path, sums_path = map(Path, sys.argv[1:])
lines = []
for path in (zip_path, tgz_path):
    lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")
sums_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

echo "Created:"
echo "  $ZIP"
echo "  $TGZ"
echo "  $SUMS"
