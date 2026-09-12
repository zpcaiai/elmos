#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"
shift || true
RUN=0
if [[ "${1:-}" == "--run" ]]; then
  RUN=1
fi
ROOT="$(cd "$ROOT" && pwd)"
ROUTER="$ROOT/.agents/skills/elmos-auto-skill-router/scripts/route_skills.py"

if [[ ! -f "$ROUTER" ]]; then
  echo "ERROR: elmos-auto-skill-router is not installed in $ROOT" >&2
  exit 2
fi

ROUTED="$(python3 "$ROUTER" --root "$ROOT" --task "continue" --remember)"
PROMPT=$(cat <<EOF
Continue the current repository work.

Follow the automatic skill-routing rules in .agents/AGENTS.md.
Inspect .agents/skills-index.json, .elmos progress/state files, git status/diff, tests, TODOs, and existing implementation before deciding what to do next.
Automatically load and compose all materially relevant installed skills. Do not ask me to name a skill when repository state determines it.
Continue the current incomplete or next dependency-ready work package.
Do not treat file existence or generated reports as proof. Actually execute available validation and report exact commands, exit codes, test counts, blockers, and remaining work.

Local deterministic routing hint:
$ROUTED
EOF
)

if [[ "$RUN" -eq 1 ]]; then
  if ! command -v agy >/dev/null 2>&1; then
    echo "ERROR: agy CLI not found. Prompt follows:" >&2
    printf '%s\n' "$PROMPT"
    exit 3
  fi
  cd "$ROOT"
  exec agy -p "$PROMPT"
else
  printf '%s\n' "$PROMPT"
fi
