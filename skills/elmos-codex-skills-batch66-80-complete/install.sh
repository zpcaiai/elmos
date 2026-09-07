#!/usr/bin/env bash
set -euo pipefail
TARGET="${1:-$HOME/.codex/skills}"; shift || true; OVERWRITE=0; BATCH=""
while (($#)); do case "$1" in --overwrite) OVERWRITE=1;; --batch) shift; BATCH="${1:?missing batch}";; *) echo "unknown $1" >&2;exit 2;; esac; shift; done
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; mkdir -p "$TARGET"; count=0
for src in "$ROOT"/agent-skills/runtime/*; do [[ -d "$src" ]]||continue; name="$(basename "$src")"; [[ -z "$BATCH" || "$name" == b"$BATCH"-* ]]||continue; dst="$TARGET/$name"; if [[ -e "$dst" && "$OVERWRITE" -ne 1 ]];then echo "Refusing existing Skill: $dst" >&2;exit 3;fi; rm -rf "$dst";cp -R "$src" "$dst";count=$((count+1));done
[[ "$count" -gt 0 ]]||{ echo "No Skills selected" >&2;exit 4;};echo "Installed $count Skills into $TARGET"
