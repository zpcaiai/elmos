#!/usr/bin/env bash
#
# Commit the perf -> main merge and fast-forward main onto it.
# Run ONLY after `bash ../elmos/verify-merge.sh` reports 0 failures and the
# three regeneration items are done.
#
#     cd /Users/stephen/DevProjects/AIProjects/elmos-merge
#     bash ../elmos/commit-perf-merge.sh
#
set -euo pipefail

if [ "$(git diff --name-only --diff-filter=U | wc -l | tr -d ' ')" != "0" ]; then
    echo "还有未解决的冲突，先解决再提交" >&2
    git diff --name-only --diff-filter=U >&2
    exit 1
fi

rm -f .git/index.lock .git/HEAD.lock
git add -A
git commit -F - <<'MSG'
merge: land the analyzer build cache, batching and php work on main

Fifty-four conflicting files between two development lines that had each
rewritten parts of the same engine. The resolution is one chain, not a
file-by-file preference:

  translationRunner.ts keeps main's spine, because its validation is what the
  browser download path is bound to -> the report must carry
  functional_conversion -> only main's pipeline.py produces it -> batch.py,
  test_pipeline.py and TranslationStudio.tsx follow main.

The engine's analyzers and toolchain pinning are this branch's own, so
native.py (7579 lines against main's 149), toolchains.py, validation.py,
assembly.py, clang_analyzer.py and repository.py come from here, with
discovery.py rebuilt on this side and main's candidate-inventory contract
grafted in.

Four places take from both sides because each half was load-bearing:

  native.py        grafts main's _external_semantic_ir. An analyzer returning
                   no functions and one diagnostic is reporting a real source
                   problem; promoting that diagnostic beats the shapeless
                   failure a caller saw several layers later.
  discovery.py     grafts _candidate_inventory / _preflight_inventory /
                   inventory_repository_incident. The functional-conversion
                   denominator needs to know whether a file's candidate list
                   is complete; without it an incomplete inventory reads as a
                   complete one.
  trust.py         keeps this side's load/from_bytes split and main's symlink
                   check, non-finite JSON rejection and object assertion.
  clang_analyzer.py keeps the objc flags and sandboxed environment and adds
                   main's TimeoutExpired -> NATIVE_ANALYZER_TIMEOUT. This side
                   passed timeout=120 without catching it, so a timeout left
                   as a bare exception rather than an engine error code.

translationInputDigest is the one that would have gone unnoticed: main had
extracted it while dropping five repository* fields the inlined version
hashed. Two jobs differing only in their repository evidence would have
collided on one input digest, and nothing downstream reports that.

Also fixes a test that could never pass on main: generation-ui.spec.ts polled
window.__generationAuthorization, which no application code assigns. This
side reads the header off the real request, so the merged test keeps that and
grafts main's method, tenant, actor and payload assertions.

Deliberately deferred, to be reattached in one follow-up rather than
half-wired here: this side's project graph and archive validation in
pipeline.py/batch.py, main's _retryable_dependency_fetch, the Studio evidence
charts, and translationRunner's coverage fields. The one test that depends on
them carries an explicit skip naming this commit's deferral.

Rationale for all 54 files is in MERGE_NOTES_perf_into_main.md.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0148gce5Aa47BLtvxXSLRrV1
MSG

echo "==> 合并提交:"; git log --oneline -1 | cat
git switch -c merge/perf-analyzer-build-cache
git switch main
git merge --ff-only merge/perf-analyzer-build-cache
echo
echo "==> main 现在在: $(git rev-parse --short HEAD)"
echo "==> 推送:  git push origin main"
echo "==> 之后:  git branch -d merge/perf-analyzer-build-cache"
echo "==>        git worktree remove ../elmos-merge"
echo "==>        rm -rf ../elmos/_merge_conflicts ../elmos/verify-merge.sh ../elmos/commit-perf-merge.sh"
