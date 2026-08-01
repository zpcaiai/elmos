#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
DEST="${1:-$HOME/.codex/skills}"
MODE="${2:-}"
mkdir -p "$DEST"
python3 "$ROOT/scripts/validate_package.py"

RUNTIME_DEST="$DEST/.repository-migration-platform-runtime"
if [ -e "$RUNTIME_DEST" ] && [ "$MODE" != "--overwrite" ]; then
  if ! cmp -s "$ROOT/scripts/migration_platform.py" "$RUNTIME_DEST/migration_platform.py" || \
     ! cmp -s "$ROOT/scripts/transaction_store.py" "$RUNTIME_DEST/transaction_store.py" || \
     ! cmp -s "$ROOT/trust-policy.json" "$RUNTIME_DEST/trust-policy.json" || \
     ! cmp -s "$ROOT/manifest.json" "$RUNTIME_DEST/manifest.json" || \
     ! diff -qr "$ROOT/schemas" "$RUNTIME_DEST/schemas" >/dev/null || \
     ! diff -qr "$ROOT/agent-skills/runtime" "$RUNTIME_DEST/agent-skills/runtime" >/dev/null; then
    echo "ERROR: installed shared runtime differs; review and rerun with --overwrite" >&2
    exit 2
  fi
else
  staging="$(mktemp -d "$DEST/.repository-migration-platform-runtime.XXXXXX")"
  trap 'rm -rf "$staging"' EXIT
  cp "$ROOT/scripts/migration_platform.py" "$staging/migration_platform.py"
  cp "$ROOT/scripts/transaction_store.py" "$staging/transaction_store.py"
  cp "$ROOT/manifest.json" "$staging/manifest.json"
  cp "$ROOT/trust-policy.json" "$staging/trust-policy.json"
  cp -R "$ROOT/schemas" "$staging/schemas"
  mkdir -p "$staging/agent-skills"
  cp -R "$ROOT/agent-skills/runtime" "$staging/agent-skills/runtime"
  chmod +x "$staging/migration_platform.py"
  rm -rf "$RUNTIME_DEST"
  mv "$staging" "$RUNTIME_DEST"
  trap - EXIT
fi

count=0
for src in "$ROOT"/agent-skills/runtime/*; do
  [ -d "$src" ] || continue
  name="$(basename "$src")"
  dst="$DEST/$name"
  if [ -e "$dst" ] && [ "$MODE" != "--overwrite" ]; then
    if diff -qr "$src" "$dst" >/dev/null; then
      echo "SKIP identical: $name"
      continue
    fi
    echo "ERROR: installed Skill differs: $name (review and use --overwrite)" >&2
    exit 2
  fi
  rm -rf "$dst"
  cp -R "$src" "$dst"
  count=$((count+1))
done
echo "Installed $count skills into $DEST"
echo "Shared runtime: $RUNTIME_DEST/migration_platform.py"
