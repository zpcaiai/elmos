#!/usr/bin/env bash
set -euo pipefail
TARGET="${1:-$HOME/.codex/skills}"
OVERWRITE="${2:-}"
mkdir -p "$TARGET"
for d in agent-skills/runtime/*; do
  name="$(basename "$d")"
  if [[ -e "$TARGET/$name" && "$OVERWRITE" != "--overwrite" ]]; then
    echo "Refusing to overwrite $TARGET/$name" >&2
    exit 1
  fi
  rm -rf "$TARGET/$name"
  cp -R "$d" "$TARGET/$name"
done
echo "Installed 16 Batch 56 Skills into $TARGET"
