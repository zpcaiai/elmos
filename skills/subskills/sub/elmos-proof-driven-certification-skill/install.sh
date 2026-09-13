#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: ./install.sh <project-root> [--agents]

Installs the skill into:
  <project-root>/.agents/skills/elmos-proof-driven-certification/

--agents  Append the Elmos non-self-certification block to .agents/AGENTS.md
          if the guarded block is not already present.
USAGE
}

if [[ $# -lt 1 ]]; then
  usage
  exit 2
fi

TARGET="$1"
WITH_AGENTS="false"
if [[ "${2:-}" == "--agents" ]]; then
  WITH_AGENTS="true"
elif [[ $# -gt 1 ]]; then
  usage
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_SKILL="$SCRIPT_DIR/skill"
DEST_SKILL="$TARGET/.agents/skills/elmos-proof-driven-certification"

if [[ ! -d "$TARGET" ]]; then
  echo "ERROR: project root does not exist: $TARGET" >&2
  exit 1
fi

mkdir -p "$DEST_SKILL"
cp -R "$SOURCE_SKILL"/. "$DEST_SKILL"/
chmod +x "$DEST_SKILL/scripts/validate_package.sh" "$DEST_SKILL/scripts/scaffold_trust_core.py"

echo "Installed skill: $DEST_SKILL"

if [[ "$WITH_AGENTS" == "true" ]]; then
  mkdir -p "$TARGET/.agents"
  AGENTS_FILE="$TARGET/.agents/AGENTS.md"
  touch "$AGENTS_FILE"
  if grep -q 'ELMOS_EXECUTION_TRUTH_BEGIN' "$AGENTS_FILE"; then
    echo "AGENTS.md already contains Elmos execution-truth rules; not appending again."
  else
    {
      echo
      cat "$SCRIPT_DIR/AGENTS.snippet.md"
      echo
    } >> "$AGENTS_FILE"
    echo "Appended Elmos execution-truth rules: $AGENTS_FILE"
  fi
fi

echo
echo "Next:"
echo "  cd \"$TARGET\""
echo "  .agents/skills/elmos-proof-driven-certification/scripts/validate_package.sh .agents/skills/elmos-proof-driven-certification"
echo
echo "Antigravity prompt:"
echo "  Use the elmos-proof-driven-certification skill and implement the next incomplete work package in dependency order."
