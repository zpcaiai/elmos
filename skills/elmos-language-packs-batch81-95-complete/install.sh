#!/usr/bin/env bash
set -euo pipefail
DEST="${1:-$HOME/.codex/skills}"
mkdir -p "$DEST"
count=0
while IFS= read -r -d '' file; do
  skill_dir="$(dirname "$file")"
  name="$(basename "$skill_dir")"
  rm -rf "$DEST/$name"
  cp -R "$skill_dir" "$DEST/$name"
  count=$((count+1))
done < <(find skills -name SKILL.md -print0 | sort -z)
echo "Installed $count ELMOS Batch 81-95 Skills into $DEST"
