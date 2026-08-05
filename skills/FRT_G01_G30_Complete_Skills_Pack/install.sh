#!/usr/bin/env bash
set -euo pipefail
DEST="${1:-$HOME/.codex/skills}"
MODE="${2:-}"
mkdir -p "$DEST"
for d in skills/*; do
  [ -d "$d" ] || continue
  name="$(basename "$d")"
  if [ -e "$DEST/$name" ] && [ "$MODE" != "--overwrite" ]; then
    echo "SKIP existing: $name"
    continue
  fi
  rm -rf "$DEST/$name"
  cp -R "$d" "$DEST/$name"
  echo "INSTALLED: $name"
done
