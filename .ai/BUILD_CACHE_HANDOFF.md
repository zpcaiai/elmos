# Build-cache v1.2 handoff

This handoff is synchronized with `BUILD_CACHE_PROGRESS.md`,
`BUILD_CACHE_EVIDENCE.md`, `BUILD_CACHE_IMPLEMENTATION_STATUS.md`,
`BUILD_CACHE_TASK.md` and `BUILD_CACHE_TEST_RESULTS.md`.

- Snapshot: **2026-08-26 Asia/Shanghai**
- Branch: `perf/analyzer-build-cache-and-batching`
- Code commit: `ea894caacf414a2676226c8297d6e5fcfd9c569b`
- Archive SHA-256: `dde312b55a95cbc7af6753ec88f07833e93ffa296b782ddcf3ef1a6470b73cb7`
- Local PostgreSQL receipt: `sha256:d1d055932032e23dd0a2c181ff1bd7ca3e64847325b28792fcfa49c52fcb3503`
- Local implementation: `COMPLETE_VERIFIED`
- External evidence: `NOT_RUN`; certification: `NOT_CERTIFIED`

## What is complete

The repository now contains the v1.2 cache-parity verticals as real, typed
code rather than declarations: provider-safe prompt boundaries, context event
projection, environment identity/sealing/restore, affinity singleflight and
diagnostics, parity metadata and API, a signed five-layer composition root,
durable harness/SLO jobs, strict idempotency/replay reconciliation, PostgreSQL
qualification and GC retention roots. All BC-01…BC-30 statuses are in the
progress ledger; the implementation matrix and acceptance evidence are kept in
the companion files above.

The final local checks are:

```text
focused cache pack: 279 passed, 3 skipped, 0 failed
ruff check src tests tools: All checks passed!
mypy src: Success: no issues found in 74 source files
OpenAPI root/data mirror: byte-identical (8 paths; both job routes present)
```

The disposable PostgreSQL qualifier ran metadata-store 65/65 and live SLO 3/3
against PostgreSQL 17.5 (Homebrew), CPython 3.12.12 and psycopg 3.3.4. The
cluster was socket-only, temporary, `fsync=on`, `synchronous_commit=on`, used
no external DSN, performed no production writes and tore down completely. The
receipt source revision equals the code SHA exactly.

## Scoped Git closeout

The code commit contains only the explicit build-cache engine files listed in
the task execution record. The synchronized documentation closeout contains
only these six paths:

```text
.ai/BUILD_CACHE_PROGRESS.md
.ai/BUILD_CACHE_EVIDENCE.md
.ai/BUILD_CACHE_IMPLEMENTATION_STATUS.md
.ai/BUILD_CACHE_HANDOFF.md
.ai/BUILD_CACHE_TASK.md
.ai/BUILD_CACHE_TEST_RESULTS.md
```

Unrelated dirty files in the shared worktree are intentionally preserved. Do
not use `git add .`, broad stashes, destructive resets, force-pushes or cleanup
commands. Before delivery, verify:

```bash
git diff --cached --name-only
git diff --cached --check
git rev-parse HEAD
git rev-parse @{u}
git ls-remote origin refs/heads/perf/analyzer-build-cache-and-batching
git status --porcelain=v1
```

The first three SHA values must match after the push. The index must be empty;
unrelated pre-existing worktree changes may remain visible in `git status`.

## Explicit remaining work

1. Run only with an authorized provider/runtime environment: real
   OpenAI/Anthropic/self-hosted calls, provider cache accounting, external
   images, multi-host fleet, representative/holdout parity corpora, CI and
   rollout evidence are still `NOT_RUN`.
2. Have an independent verifier inspect the immutable artifacts, raw logs,
   authorization, environment and replay receipts. The local qualification is
   `LOCAL_EXECUTED_SELF_ATTESTED` only.
3. Use the governing parity/certification gate after all required evidence
   roles exist. Until then `NOT_CERTIFIED` is the only valid certification
   state.

The earlier full non-native aggregate (`1734 passed, 51 skipped, 1 unrelated
pre-existing policy failure`) and interrupted native-toolchain sweep are kept
as historical evidence in `BUILD_CACHE_TEST_RESULTS.md`; neither is silently
re-run or relabelled.
