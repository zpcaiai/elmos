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
# Run from the repository root.  Nothing here touches git.
set -uo pipefail
cd "$(dirname "$0")/../.." 2>/dev/null || true
STAMP="$(date +%Y-%m-%d)"
ART=".ai/measurement-2026-08-26"
mkdir -p "${ART}/mac-${STAMP}"
FAILED=0
step() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }

step "1/6  polyglot-route-engine suite -- DO NOT COUNT THE F CHARACTERS"
# The progress bar is meaningless here: this suite has a large standing set of
# failures.  The only valid judgement is the FAILED SET, compared against a
# baseline from the same tree.  This step captures the set; step 1b diffs it.
uv --directory engines/polyglot-route-engine run --locked pytest -q -rfE \
  > "${ART}/mac-${STAMP}/polyglot-run.txt" 2>&1
grep -E '^(FAILED|ERROR)' "${ART}/mac-${STAMP}/polyglot-run.txt" | sort \
  > "${ART}/mac-${STAMP}/polyglot-failed.txt"
tail -1 "${ART}/mac-${STAMP}/polyglot-run.txt"
echo "  FAILED/ERROR entries: $(wc -l < "${ART}/mac-${STAMP}/polyglot-failed.txt")"
echo "  new tests this pass:  tests/test_unary_and_nary_boolean.py (26, all must pass)"
uv --directory engines/polyglot-route-engine run --locked \
  pytest -q tests/test_unary_and_nary_boolean.py || FAILED=1

step "1b/6  compare against a baseline from the SAME tree"
cat <<'NOTE'
  There is no committed baseline file, and comparing against one from a
  different tree is worse than not comparing. To produce one:

    git stash                       # or: git worktree add /tmp/elmos-base HEAD~1
    uv --directory engines/polyglot-route-engine run --locked pytest -q -rfE \
      2>&1 | grep -E '^(FAILED|ERROR)' | sort > /tmp/polyglot-baseline.txt
    git stash pop

  then:

    diff /tmp/polyglot-baseline.txt \
         .ai/measurement-2026-08-26/mac-DATE/polyglot-failed.txt

  An empty diff is the zero-regression result. In the cloud this pass gave
  1190 identical entries and passed 833 -> 859 (+26 = the new file).
NOTE

step "2/6  sql-dialect-engine (261 expected: 167 pre-existing + 16 + 62 + 16)"
uv --directory engines/sql-dialect-engine run --locked pytest -q || FAILED=1

step "3/6  project-synthesis-engine (148 collected: 135 pre-existing + 13)"
uv --directory engines/project-synthesis-engine run --locked pytest -q || FAILED=1

step "4/6  sql-transpiler + Batch 31 qualification"
uv --directory engines/database-data-engine/sql-transpiler run --locked pytest -q || FAILED=1

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
  --out "${REPO}/${ART}/mac-${STAMP}/differential" \
  --json "${REPO}/${ART}/mac-${STAMP}/execution-evidence.json" || FAILED=1
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

printf '\n'
if [ "${FAILED}" -eq 0 ]; then
  echo "all automated steps passed -- artefacts in ${ART}/mac-${STAMP}/"
else
  echo "at least one step failed -- see output above"
fi
exit "${FAILED}"
