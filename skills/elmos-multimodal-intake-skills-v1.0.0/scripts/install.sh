#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SOURCE="${PACKAGE_ROOT}/skills"
TARGET=""
MODE="both"
FORCE=0
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: install.sh --target PATH [--codex|--claude|--both] [--force] [--dry-run]

Installs the canonical Elmos skill directories into:
  Codex:       <target>/.agents/skills
  Claude Code: <target>/.claude/skills
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) TARGET="${2:-}"; shift 2 ;;
    --codex) MODE="codex"; shift ;;
    --claude) MODE="claude"; shift ;;
    --both) MODE="both"; shift ;;
    --force) FORCE=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ -z "$TARGET" ]]; then
  echo "--target is required" >&2
  usage
  exit 2
fi
if [[ ! -d "$TARGET" ]]; then
  echo "Target repository does not exist: $TARGET" >&2
  exit 2
fi
if [[ ! -d "$SOURCE" ]]; then
  echo "Canonical skills directory not found: $SOURCE" >&2
  exit 2
fi

copy_set() {
  local dest="$1"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    mkdir -p "$dest"
  fi
  local copied=0
  local skipped=0
  local src name target_dir

  # Shell glob order is deterministic for these ASCII skill directory names and
  # avoids GNU-only find/sort flags, so this works on macOS and Linux.
  for src in "$SOURCE"/*; do
    [[ -d "$src" ]] || continue
    name="$(basename "$src")"
    target_dir="${dest}/${name}"
    if [[ -e "$target_dir" && "$FORCE" -ne 1 ]]; then
      echo "SKIP existing: $target_dir"
      skipped=$((skipped+1))
      continue
    fi
    echo "INSTALL: $src -> $target_dir"
    if [[ "$DRY_RUN" -eq 0 ]]; then
      rm -rf "$target_dir"
      cp -R "$src" "$target_dir"
    fi
    copied=$((copied+1))
  done
  echo "Result for $dest: copied=$copied skipped=$skipped"
}

case "$MODE" in
  codex) copy_set "${TARGET}/.agents/skills" ;;
  claude) copy_set "${TARGET}/.claude/skills" ;;
  both)
    copy_set "${TARGET}/.agents/skills"
    copy_set "${TARGET}/.claude/skills"
    ;;
  *) echo "Invalid mode: $MODE" >&2; exit 2 ;;
esac

echo "Installation complete. Canonical source remains: $SOURCE"
