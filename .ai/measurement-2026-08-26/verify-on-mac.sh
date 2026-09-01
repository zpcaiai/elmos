#!/usr/bin/env bash
# Mac-side verification for the 2026-08-26 pass.  Supersedes
# .ai/measurement-2026-08-21/verify-on-mac.sh (that one is still correct for
# the 08-25 fixes; this one adds the 08-26 analyzer fixes and the 13-target
# execution differential, and fixes how step 1 is judged).
#
# Everything here has already been run in the cloud container.  What only your
# Mac can do is run it against the PINNED toolchains, and run the five targets
# no Linux container has: C#, Objective-C, Swift, Kotlin, Dart/Flutter.
#
# Run from the repository root.
#
# git: this script issues READ-ONLY, LOCK-FREE git queries only --
# `GIT_OPTIONAL_LOCKS=0 git rev-parse` for provenance, and (only under
# --freeze) `GIT_OPTIONAL_LOCKS=0 git archive`.  Neither writes the index.
# Every git call is optional: if git is missing or fails, the run continues
# and the provenance record says so.
#
# 2026-09-01 additions (see .ai/FINDINGS-2026-09-01-gate-triage.md):
#   * mixed-tree detection.  A long run that spans somebody else's writes
#     produces numbers with no single tree behind them.  gate-triage.sh already
#     detects this and downgrades; this script did not.  It does now.
#   * the redundant `-q`.  Three of the four suites below already carry
#     `addopts = "-q ..."` in their pyproject.  Passing `-q` again on the
#     command line makes it `-qq`, and `-qq` DELETES the count line
#     ("165 passed in 3.34s").  The `FAILED`/`ERROR` short-summary lines
#     survive, so nothing looks broken -- but `tail -1` prints the progress
#     bar instead of the result, and any classifier keying on "N passed" gets
#     nothing and reports UNKNOWN.  The `-q` is now supplied by exactly one
#     place per suite, and step 0 asserts that a count line was produced.
set -uo pipefail
cd "$(dirname "$0")/../.." 2>/dev/null || true
STAMP="$(date +%Y-%m-%d)"
ART=".ai/measurement-2026-08-26"
RUN="${ART}/mac-${STAMP}"
mkdir -p "${RUN}"
FAILED=0
step() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }

MODE="${1:-}"

git_ro() { GIT_OPTIONAL_LOCKS=0 git "$@" 2>/dev/null || printf 'unavailable'; }

# ---------------------------------------------------------------- --freeze --
# The tree cannot move under a run that owns its own copy of it.  This is the
# only way to make a baseline and a head run comparable: BOTH sides must be
# exported the same way.  Read the trade-off before using it --
#   an exported tree contains ONLY TRACKED FILES.  No node_modules, no built
#   analyzer binaries, no .venv, no ~/.cache warm build caches.  Suites that
#   shell out to a toolchain will be slower and some will fail for reasons
#   that have nothing to do with the code.  That asymmetry -- baseline from
#   `git archive`, head from the live worktree -- is exactly what made the
#   08-26 "190 tests fixed by the merge" column meaningless.
# So: use --freeze for A/B differencing, where both sides pay the same cost.
# Do NOT use it to answer "does my Mac pass"; use the plain run for that.
if [ "${MODE}" = "--freeze" ]; then
  FROZEN="$(mktemp -d "${TMPDIR:-/tmp}/elmos-frozen-XXXXXX")"
  SHA="$(git_ro rev-parse --short HEAD)"
  if [ "${SHA}" = "unavailable" ]; then
    echo "--freeze needs git; cannot export a frozen tree. Aborting." >&2
    exit 2
  fi
  echo "exporting HEAD (${SHA}) to ${FROZEN} -- tracked files only"
  if ! GIT_OPTIONAL_LOCKS=0 git archive HEAD | tar -x -C "${FROZEN}"; then
    echo "git archive failed; aborting rather than running on a moving tree." >&2
    exit 2
  fi
  echo "${SHA}" > "${FROZEN}/.frozen-head-sha"
  echo "re-running inside the frozen tree; artefacts stay there."
  bash "${FROZEN}/${ART}/verify-on-mac.sh" --frozen
  rc=$?
  echo
  echo "frozen-tree artefacts:  ${FROZEN}/${RUN}/"
  echo "to keep them:           cp -R '${FROZEN}/${RUN}' '${RUN}-frozen-${SHA}'"
  exit "${rc}"
fi

# ------------------------------------------------------------- provenance --
# Recorded BEFORE any suite starts.  Without a start marker there is no way,
# afterwards, to tell a clean run from one that straddled somebody's commit.
MARKER="$(mktemp "${TMPDIR:-/tmp}/elmos-run-start-XXXXXX")"
START_ISO="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
START_EPOCH="$(date +%s)"
HEAD_START="$(git_ro rev-parse --short HEAD)"
FROZEN_NOTE="live worktree"
[ "${MODE}" = "--frozen" ] && FROZEN_NOTE="frozen export of $(cat .frozen-head-sha 2>/dev/null || echo unknown)"

# The trees whose contents these suites actually depend on.  Generated and
# cache directories are excluded: they are written BY the run and would make
# every run look mixed.
WATCH_PATHS=(
  engines/polyglot-route-engine/src        engines/polyglot-route-engine/tests
  engines/sql-dialect-engine/src           engines/sql-dialect-engine/tests
  engines/project-synthesis-engine/src     engines/project-synthesis-engine/tests
  engines/database-data-engine/sql-transpiler/src
  engines/database-data-engine/sql-transpiler/tests
)

{
  echo "run_started_utc   ${START_ISO}"
  echo "head_at_start     ${HEAD_START}"
  echo "tree              ${FROZEN_NOTE}"
  echo "host              $(uname -srm)"
} > "${RUN}/run-provenance.txt"
printf '\033[1m== 0/6  provenance ==\033[0m\n'
cat "${RUN}/run-provenance.txt"

step "1/6  polyglot-route-engine suite -- DO NOT COUNT THE F CHARACTERS"
# The progress bar is meaningless here: this suite has a large standing set of
# failures.  The only valid judgement is the FAILED SET, compared against a
# baseline from the same tree.  This step captures the set; step 1b diffs it.
# NOTE: no `-q` here.  engines/polyglot-route-engine/pyproject.toml already
# sets addopts = "-q --strict-markers"; a second -q suppresses the count line.
uv --directory engines/polyglot-route-engine run --locked pytest -rfE \
  > "${RUN}/polyglot-run.txt" 2>&1
grep -aE '^(FAILED|ERROR)' "${RUN}/polyglot-run.txt" | sort \
  > "${RUN}/polyglot-failed.txt"
# `tail -1` is only meaningful if a count line was actually produced.  Assert it.
if grep -aqE '^[0-9]+ (passed|failed)|[0-9]+ (passed|failed)[,.]| in [0-9.]+s$' "${RUN}/polyglot-run.txt"; then
  tail -1 "${RUN}/polyglot-run.txt"
else
  echo "  !! no pytest count line in polyglot-run.txt."
  echo "  !! Almost always a doubled -q (-qq deletes it). The FAILED/ERROR set"
  echo "  !! below is still valid; the totals are not recoverable from this log."
  FAILED=1
fi
echo "  FAILED/ERROR entries: $(wc -l < "${RUN}/polyglot-failed.txt")"
echo "  new tests this pass:  tests/test_unary_and_nary_boolean.py (26, all must pass)"
uv --directory engines/polyglot-route-engine run --locked \
  pytest tests/test_unary_and_nary_boolean.py || FAILED=1

step "1b/6  compare against a baseline from the SAME tree"
cat <<'NOTE'
  There is no committed baseline file, and comparing against one from a
  different tree is worse than not comparing.

  The cheapest honest baseline is a frozen export -- and the head side must be
  exported the SAME way, or the diff measures the environment, not the code:

    bash .ai/measurement-2026-08-26/verify-on-mac.sh --freeze   # this tree
    # ... and the same on the base revision, then diff the two
    # polyglot-failed.txt files.

  Or, without freezing (faster, valid only if nothing writes to the tree
  while it runs -- step 7 below tells you whether that held):

    git worktree add /tmp/elmos-base HEAD~1
    uv --directory engines/polyglot-route-engine run --locked pytest -rfE \
      2>&1 | grep -aE '^(FAILED|ERROR)' | sort > /tmp/polyglot-baseline.txt

  then:

    diff /tmp/polyglot-baseline.txt \
         .ai/measurement-2026-08-26/mac-DATE/polyglot-failed.txt

  An empty diff is the zero-regression result. In the cloud this pass gave
  1190 identical entries and passed 833 -> 859 (+26 = the new file).
NOTE

step "2/6  sql-dialect-engine (261 expected: 167 pre-existing + 16 + 62 + 16)"
# -q IS correct here: this project has no addopts.
uv --directory engines/sql-dialect-engine run --locked pytest -q || FAILED=1

step "3/6  project-synthesis-engine (148 collected: 135 pre-existing + 13)"
# no -q: pyproject already sets addopts = "-q --strict-markers".
uv --directory engines/project-synthesis-engine run --locked pytest || FAILED=1

step "4/6  sql-transpiler + Batch 31 qualification"
# no -q: pyproject already sets addopts = "-q".
uv --directory engines/database-data-engine/sql-transpiler run --locked pytest || FAILED=1

step "5/6  capability probe -- the admission surface moved AGAIN"
# 08-25 the docstring fix moved it; 08-26 signed literals, n-ary boolean
# chains and `not` moved it again. The checked-in matrix is stale until this
# is re-run.
make capability-probe-json > ".ai/capability-probe-${STAMP}.json" \
  && echo "wrote .ai/capability-probe-${STAMP}.json" || FAILED=1

step "6/6  13-target execution differential (THE reason to run this on a Mac)"
# canonical.evaluate is the reference -- not any target.
# In the cloud 7 of 13 agreed; csharp / objc / swift / kotlin / flutter had no
# toolchain there. Your Mac has all five pinned.
# ABSOLUTE paths on purpose: `uv --directory X` changes the working
# directory to X before running, so a repository-root-relative path here
# resolves under engines/polyglot-route-engine/ and the script "does not
# exist". Same trap as the `--locked` note in step 6 of the 08-21 script.
REPO="$(pwd)"
uv --directory engines/polyglot-route-engine run --locked python \
  "${REPO}/${ART}/differential_execution.py" \
  --out "${REPO}/${RUN}/differential" \
  --json "${REPO}/${RUN}/execution-evidence.json" || FAILED=1
cat <<'NOTE'
  Read it like this:
    AGREES_WITH_CANONICAL   the target computes what the specification says
    EMISSION_REFUSED        expected for typescript/react on the `full` suite:
                            -9223372036854775808 is past MAX_SAFE_INTEGER and
                            refusing is CORRECT. They must AGREE on `safe_integer`.
    DIVERGES                a real defect -- report it, do not average it away
    NOT_RUN                 never counts as a pass; the reason is in the JSON
  Every row records which binary was used and its version, GRADED:
    EXACT:   the engine's own exact_toolchain() accepted it -- version AND
             sha256 checked against the repository pin (Xcode+SDK too, for
             cpp/objc/swift). This is pinned-toolchain evidence.
    PINNED:  exactly one version directory under the toolchain root. The path
             is named; nothing about its contents was verified.
    PATH:    whatever `which` found. Mac-runtime evidence only.
    ENV:     you named it yourself via ELMOS_DIFF_<LANG>. Asserts nothing.
  A weaker grade ALWAYS carries the reason EXACT was unavailable in parentheses
  -- e.g. `PATH:/usr/bin/clang++ (EXACT_REFUSED:EXACT_TOOLCHAIN_APPLE_PROFILE_
  MISMATCH:cpp:...)`. If you see that, the row ran on a binary the repository
  does not pin, and the code tells you exactly which pin failed.
NOTE

# ------------------------------------------------------- mixed-tree check --
# Runs BEFORE the verdict, so the verdict can be downgraded.  A number
# produced across somebody else's write has no tree behind it and must not be
# quoted, however green it looks.
step "7/6  mixed-tree check -- did the tree hold still?"
END_ISO="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
HEAD_END="$(git_ro rev-parse --short HEAD)"
ELAPSED=$(( $(date +%s) - START_EPOCH ))
MIXED=0
WRITTEN="${RUN}/tree-writes-during-run.txt"
: > "${WRITTEN}"
for p in "${WATCH_PATHS[@]}"; do
  [ -d "${p}" ] || continue
  find "${p}" -type f -newer "${MARKER}" 2>/dev/null
done | grep -av -e '__pycache__' -e '/\.venv/' -e '/\.pytest_cache/' \
                -e '/\.ruff_cache/' -e '/\.mypy_cache/' -e '/node_modules/' \
                -e '\.pyc$' | sort > "${WRITTEN}"
NWRITES="$(wc -l < "${WRITTEN}" | tr -d ' ')"
[ "${NWRITES}" -gt 0 ] && MIXED=1
if [ "${HEAD_START}" != "${HEAD_END}" ] \
   && [ "${HEAD_START}" != "unavailable" ] && [ "${HEAD_END}" != "unavailable" ]; then
  MIXED=1
fi
{
  echo "run_ended_utc     ${END_ISO}"
  echo "elapsed_seconds   ${ELAPSED}"
  echo "head_at_end       ${HEAD_END}"
  echo "source_writes     ${NWRITES}"
  echo "mixed_tree        ${MIXED}"
} >> "${RUN}/run-provenance.txt"
echo "  window        ${START_ISO} -> ${END_ISO}  (${ELAPSED}s)"
echo "  HEAD          ${HEAD_START} -> ${HEAD_END}"
echo "  source writes ${NWRITES}  (${WRITTEN})"
if [ "${MIXED}" -eq 1 ]; then
  : > "${RUN}/.mixed-tree"
  {
    echo "window ${START_ISO} -> ${END_ISO}"
    echo "head ${HEAD_START} -> ${HEAD_END}"
    echo "source_writes ${NWRITES}"
  } >> "${RUN}/.mixed-tree"
  head -20 "${WRITTEN}" | sed 's/^/    /'
  [ "${NWRITES}" -gt 20 ] && echo "    ... $(( NWRITES - 20 )) more"
fi

printf '\n'
if [ "${MIXED}" -eq 1 ]; then
  printf '\033[1mMIXED TREE -- these numbers describe no single tree.\033[0m\n'
  echo "The tree changed under this run (see ${RUN}/.mixed-tree)."
  echo "Every result above is UNKNOWN, including the green ones: no two steps"
  echo "here are guaranteed to have run against the same source. Re-run with"
  echo "  bash ${ART}/verify-on-mac.sh --freeze"
  echo "or re-run when nothing else is writing to the repository."
  exit 3
fi
if [ "${FAILED}" -eq 0 ]; then
  echo "all automated steps passed -- artefacts in ${RUN}/"
else
  echo "at least one step failed -- see output above"
fi
exit "${FAILED}"
