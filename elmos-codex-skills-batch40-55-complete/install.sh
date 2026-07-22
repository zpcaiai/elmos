#!/usr/bin/env bash
set -euo pipefail
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/agent-skills/runtime"
TARGET_DIR="${1:-${HOME}/.codex/skills}"
OVERWRITE="${2:-}"
mkdir -p "$TARGET_DIR"
count=0
for skill in "$SOURCE_DIR"/*; do
  [[ -d "$skill" ]] || continue
  name="$(basename "$skill")"
  dest="$TARGET_DIR/$name"
  if [[ -e "$dest" && "$OVERWRITE" != "--overwrite" ]]; then
    echo "ERROR: destination already exists: $dest" >&2
    echo "Re-run with: $0 '$TARGET_DIR' --overwrite" >&2
    exit 1
  fi
  rm -rf "$dest"
  cp -R "$skill" "$dest"
  count=$((count+1))
done
echo "Installed $count ELMOS Skills into $TARGET_DIR"
