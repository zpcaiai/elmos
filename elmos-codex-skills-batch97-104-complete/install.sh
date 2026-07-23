#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${1:-${CODEX_SKILLS_DIR:-${HOME}/.codex/skills}}"
shift || true
BATCH=""
OVERWRITE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --batch)
      BATCH="${2:?missing batch}"
      shift 2
      ;;
    --overwrite)
      OVERWRITE=1
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -n "$BATCH" ]] && { (( BATCH < 97 )) || (( BATCH > 104 )); }; then
  echo "--batch must be an integer from 97 through 104" >&2
  exit 2
fi

VALIDATE_ARGS=()
if [[ -n "$BATCH" ]]; then
  VALIDATE_ARGS=(--batch "$BATCH")
fi
"$ROOT/validate.sh" "${VALIDATE_ARGS[@]}"

INSTALL_ARGS=(--root "$ROOT" --target "$TARGET")
if [[ -n "$BATCH" ]]; then
  INSTALL_ARGS+=(--batch "$BATCH")
fi
if [[ "$OVERWRITE" -eq 1 ]]; then
  INSTALL_ARGS+=(--overwrite)
fi
python3 "$ROOT/scripts/install_skills.py" "${INSTALL_ARGS[@]}"
