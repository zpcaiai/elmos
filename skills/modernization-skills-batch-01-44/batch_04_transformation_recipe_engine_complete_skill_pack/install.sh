#!/usr/bin/env bash
set -euo pipefail
TARGET="${1:-$HOME/.codex/skills}"
mkdir -p "$TARGET"
for d in skills/*; do
  name="$(basename "$d")"
  if [ -e "$TARGET/$name" ]; then echo "destination exists: $TARGET/$name" >&2; exit 2; fi
  cp -R "$d" "$TARGET/$name"
done
echo "Installed 25 skills into $TARGET"
