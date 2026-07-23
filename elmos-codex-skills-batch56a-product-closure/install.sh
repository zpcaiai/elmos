#!/usr/bin/env bash
set -euo pipefail
TARGET="${1:-$HOME/.codex/skills}"
OVERWRITE="${2:-}"
mkdir -p "$TARGET"
for skill_dir in "$(dirname "$0")"/agent-skills/runtime/*; do
 name="$(basename "$skill_dir")"; dest="$TARGET/$name"
 if [[ -e "$dest" && "$OVERWRITE" != "--overwrite" ]]; then echo "Refusing overwrite: $dest" >&2; exit 2; fi
 rm -rf "$dest"; cp -R "$skill_dir" "$dest"
done
echo "Installed 16 Batch 56A Skills into $TARGET"
