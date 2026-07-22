#!/usr/bin/env bash
set -euo pipefail
TARGET="${1:-$HOME/.codex/skills}"
mkdir -p "$TARGET"
count=0
for d in agent-skills/runtime/*; do
  cp -R "$d" "$TARGET/"
  count=$((count+1))
done
echo "Installed $count test Skills into $TARGET"
