#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${1:-$HOME/.codex/skills}"
shift || true
BATCH=""; OVERWRITE=0
while (($#)); do
  case "$1" in
    --batch) BATCH="${2:?batch required}"; shift 2 ;;
    --overwrite) OVERWRITE=1; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
mkdir -p "$TARGET"
count=0
for src in "$ROOT"/agent-skills/runtime/*; do
  [[ -d "$src" ]] || continue
  name="$(basename "$src")"
  if [[ -n "$BATCH" && ( "$name" != tst-b"$BATCH"-* || "$name" == tst-b66-80-* ) ]]; then continue; fi
  dst="$TARGET/$name"
  if [[ -e "$dst" && "$OVERWRITE" -ne 1 ]]; then echo "destination exists: $dst" >&2; exit 3; fi
  rm -rf "$dst"; cp -R "$src" "$dst"; count=$((count+1))
done
if [[ -n "$BATCH" && "$count" -ne 1 ]]; then echo "expected 1 Batch skill, installed $count" >&2; exit 4; fi
echo "Installed $count test Skills into $TARGET"
