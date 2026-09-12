#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
TARGET="$TMP/target"; mkdir -p "$TARGET"; git -C "$TARGET" init -q
"$ROOT/install.sh" --repo "$TARGET" --host both --profile p0 --dry-run >/dev/null
"$ROOT/install.sh" --repo "$TARGET" --host both --profile p0 >/dev/null
test -f "$TARGET/.agents/skills/elmos-fde-package-navigator/SKILL.md"
test -f "$TARGET/.elmos/extensions/elmos-fde-autonomous-delivery-repository-refactoring-skills-v5.2.0/catalog/package.yaml"
FIRST="$TARGET/.agents/skills/elmos-fde-package-navigator/SKILL.md"; printf '\nlocal modification\n' >> "$FIRST"
"$ROOT/uninstall.sh" --repo "$TARGET" >/tmp/elmos-fde-uninstall-smoke.json
test -f "$FIRST"

TARGET2="$TMP/target2"; mkdir -p "$TARGET2/.agents/skills/elmos-fde-package-navigator"; git -C "$TARGET2" init -q
printf 'original local file\n' > "$TARGET2/.agents/skills/elmos-fde-package-navigator/SKILL.md"
"$ROOT/install.sh" --repo "$TARGET2" --host codex --profile p0 --force --allow-dirty >/dev/null
"$ROOT/uninstall.sh" --repo "$TARGET2" >/dev/null
grep -q 'original local file' "$TARGET2/.agents/skills/elmos-fde-package-navigator/SKILL.md"
echo "PASS: install/uninstall dry-run, modified-file preservation and backup restore"
