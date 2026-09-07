#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$ROOT/.agents/skills"
TARGET=""

usage() {
  cat <<'EOF'
Usage:
  ./install.sh --codex
  ./install.sh --claude
  ./install.sh --target /path/to/skills

--codex   installs into ${CODEX_HOME:-$HOME/.codex}/skills
--claude  installs into ${CLAUDE_HOME:-$HOME/.claude}/skills
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

mkdir -p "$TARGET"
for skill in "$SOURCE"/*; do
  [[ -d "$skill" ]] || continue
  name="$(basename "$skill")"
  rm -rf "$TARGET/$name"
  cp -R "$skill" "$TARGET/$name"
done

echo "Installed 12 Elmos Skills into $TARGET"
