#!/usr/bin/env bash
set -euo pipefail
DEST="${1:-$HOME/.codex/skills}"
OVERWRITE="${2:-}"
mkdir -p "$DEST"
for d in agent-skills/runtime/*; do
  [ -d "$d" ] || continue
  name="$(basename "$d")"
  target="$DEST/$name"
  if [ -e "$target" ] && [ "$OVERWRITE" != "--overwrite" ]; then
    echo "Collision: $target (use --overwrite only after review)" >&2
    exit 2
  fi
  rm -rf "$target"
  cp -R "$d" "$target"
done
echo "Installed 88 ELMOS test Skills into $DEST"
