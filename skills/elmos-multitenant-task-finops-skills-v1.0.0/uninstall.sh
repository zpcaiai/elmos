#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$ROOT/.agents/skills"
TARGET=""

usage() {
  cat <<'EOF'
Usage:
  ./uninstall.sh --codex
  ./uninstall.sh --claude
  ./uninstall.sh --target /path/to/skills
EOF
}

case "${1:-}" in
  --codex) TARGET="${CODEX_HOME:-$HOME/.codex}/skills" ;;
  --claude) TARGET="${CLAUDE_HOME:-$HOME/.claude}/skills" ;;
  --target)
    [[ $# -eq 2 ]] || { usage >&2; exit 2; }
    TARGET="$2"
    ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac

removed=0
for skill in "$SOURCE"/*; do
  [[ -d "$skill" ]] || continue
  name="$(basename "$skill")"
  if [[ -e "$TARGET/$name" ]]; then
    rm -rf "$TARGET/$name"
    removed=$((removed + 1))
  fi
done

echo "Removed $removed Elmos Skills from $TARGET"
