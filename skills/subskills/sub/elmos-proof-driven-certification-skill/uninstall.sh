#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: ./uninstall.sh <project-root>" >&2
  exit 2
fi

TARGET="$1"
DEST="$TARGET/.agents/skills/elmos-proof-driven-certification"
if [[ -d "$DEST" ]]; then
  rm -rf "$DEST"
  echo "Removed: $DEST"
else
  echo "Skill not installed at: $DEST"
fi

echo "Note: this does not edit .agents/AGENTS.md. Remove the guarded ELMOS_EXECUTION_TRUTH block manually if desired."
