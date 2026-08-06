#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${1:-$HOME/.codex/skills}"
shift || true
OVERWRITE=0; BATCH=""
while [[ $# -gt 0 ]]; do case "$1" in --overwrite) OVERWRITE=1;; --batch) BATCH="$2"; shift;; *) echo "unknown option: $1" >&2; exit 2;; esac; shift; done
mkdir -p "$DEST"
python3 - "$ROOT" "$DEST" "$OVERWRITE" "$BATCH" <<'PY2'
import json,shutil,sys
from pathlib import Path
root,dest,overwrite,batch=Path(sys.argv[1]),Path(sys.argv[2]),int(sys.argv[3]),sys.argv[4]
m=json.loads((root/'manifest.json').read_text()); selected=[]
for b in m['batches']:
 if batch and str(b['batch'])!=batch: continue
 selected += b['skills']
for s in selected:
 src=root/'agent-skills/runtime'/s['name']; dst=dest/s['name']
 if dst.exists() and not overwrite: raise SystemExit(f'collision: {dst}; use --overwrite after review')
 if dst.exists(): shutil.rmtree(dst)
 shutil.copytree(src,dst)
print(f'installed {len(selected)} skills into {dest}')
PY2
