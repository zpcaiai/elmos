#!/usr/bin/env bash
# Mac-side verification for the 2026-08-25 fix pass.
#
# Everything below was already run in the cloud container; what only your Mac
# can do is run it against the PINNED toolchains. The cloud numbers are in
# .ai/FINDINGS-2026-08-25-fixes.md and .ai/FINDINGS-2026-08-25-subset-widening.md
# -- this script produces the same measurements with the pins honoured.
#
# Run from the repository root. Nothing here writes to git.
set -uo pipefail
cd "$(dirname "$0")/../.." 2>/dev/null || true
FAILED=0
step() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }

step "1/6  polyglot-route-engine test suite (pinned toolchains)"
# In the cloud 1198 of these fail purely because the macOS toolchains are
# absent. On your Mac that number is the real one.
uv --directory engines/polyglot-route-engine run --locked pytest -q || FAILED=1

step "2/6  sql-dialect-engine test suite"
# 261 tests expected: 167 pre-existing + 16 IF NOT EXISTS + 62 CHECK predicates
# + 16 scan recovery.
uv --directory engines/sql-dialect-engine run --locked pytest -q || FAILED=1

step "3/6  project-synthesis-engine test suite"
# 148 collected expected: 135 pre-existing + 13 production relations.
uv --directory engines/project-synthesis-engine run --locked pytest -q || FAILED=1

step "4/6  sql-transpiler test suite + Batch 31 qualification"
uv --directory engines/database-data-engine/sql-transpiler run --locked pytest -q || FAILED=1

step "5/6  capability probe (the Python frontend's admission surface moved)"
# The docstring fix changes what discover_unit admits, so the checked-in
# capability matrix is stale until this is re-run.
make capability-probe-json > .ai/capability-probe-$(date +%Y-%m-%d).json && \
  echo "wrote .ai/capability-probe-$(date +%Y-%m-%d).json" || FAILED=1

step "6/6  repository admission rate, all 13 languages"
# Point --repository at whatever real repositories you want measured.
cat <<'NOTE'
  Not run automatically -- it needs you to choose the corpus. For each language:

    uv --directory engines/polyglot-route-engine run --locked python \
      tools/measure_repository_admission.py \
      --repository ~/DevProjects/AIProjects/<repo> \
      --language <python|java|go|rust|csharp|cpp|objc|swift|kotlin|php|typescript|javascript|dart> \
      --output .ai/admission-<repo>-<language>.json

  Do NOT run it as `uv run --locked python tools/...` from the repository root:
  --locked only applies inside the engine's own project, uv falls back to the
  PATH python, and it reports "No such file or directory" as if the file were
  missing.
NOTE

printf '\n'
if [ "$FAILED" -eq 0 ]; then
  echo "all automated steps passed"
else
  echo "at least one step failed -- see output above"
fi
exit "$FAILED"
