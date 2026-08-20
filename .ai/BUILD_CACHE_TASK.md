# BUILD_CACHE_TASK.md

> Active task for the `elmos-build-cache-staging-sota` skills package
> (v1.1.0, which supersedes `elmos-build-cache-staging-recovery` v1.0.0).
> Companion files: `BUILD_CACHE_IMPLEMENTATION_STATUS.md`,
> `BUILD_CACHE_TEST_RESULTS.md`, `BUILD_CACHE_EVIDENCE.md`,
> `BUILD_CACHE_HANDOFF.md`.

- **Started:** 2026-08-19
- **Second pass:** 2026-08-19 (closing the seven `PARTIAL` rows)
- **Third pass:** 2026-08-19 (closing the four that remained)
- **Fourth pass:** 2026-08-20 (the v1.1.0 SOTA package: 7 new P8 skills, plus
  wiring the policy plane into the engine rather than beside it)
- **Agent:** Claude (Cowork, cloud session)
- **Input package (passes 1–3):** `elmos-build-cache-staging-skills-v1.0.0`
  (24 skills, P0–P7)
- **Input package (pass 4):** `elmos-build-cache-staging-sota-skills-v1.1.0`
  (31 skills, P0–P8 — the original 24 at `version: 1.1.0` plus 7 new SOTA
  skills: trace/replay simulator, policy portfolio, DAG-aware prefetch,
  cost-aware admission, adaptive orchestrator, learning-augmented control,
  autotuning certification)
- **Scope agreed with the user:** implement **all 24 skills** as real code,
  land it under `engines/build-cache-engine/`, install the 24 `SKILL.md` files
  into `agent-skills/runtime/`, run the package's `./validate.sh`, and record
  progress here. The second pass adds: close every gap that was only open
  because the first environment could not prove it, and re-verify. The fourth
  pass adds: implement all 31 v1.1.0 skills, and satisfy the package's explicit
  requirement that the policy plane "must be in the repository, not a
  disconnected prototype" — so the portfolio has to be reachable from a real
  call path and from configuration, not only from a benchmark script.

## What "implemented" means for this task

The package's `AGENTS.md` is explicit: architecture prose is not completion.
For every skill the deliverable is production code in this repository plus
automated tests, failure-path verification, telemetry, documentation, rollout
controls, and machine-readable evidence. This file set is that evidence.

Status vocabulary used in the companion files is the repository's closed set:
`IMPLEMENTED` · `PARTIAL` · `STUB` · `MISSING` · `BROKEN` · `NOT VERIFIED`.

`IMPLEMENTED` requires **all** of: real logic (no TODO / `pass` /
`NotImplemented` / hardcoded success), wired into a real call chain, covered by
a test that exercises the behaviour, and an **executed** result recorded in
`BUILD_CACHE_TEST_RESULTS.md`.

## Deliverables

| Deliverable | Path |
|---|---|
| Implementation | `engines/build-cache-engine/src/elmos_build_cache/` (45 modules, 23 870 lines) |
| Tests | `engines/build-cache-engine/tests/` (41 files, 11 955 lines, 921 tests) |
| Tools | `engines/build-cache-engine/tools/cross_platform_snapshot.py` |
| SQL migrations | `engines/build-cache-engine/migrations/{postgres,sqlite}/` (6 files) |
| JSON Schemas | `engines/build-cache-engine/schemas/` — 10 files (+ packaged copy under `src/.../_data/`) |
| OpenAPI | `engines/build-cache-engine/openapi/cache-control-plane.openapi.yaml` |
| Configuration | `engines/build-cache-engine/config/elmos-cache{,.local}.yaml` |
| CLI | `elmos-cache` console script (`elmos_build_cache.cli`) |
| Skills | `agent-skills/runtime/elmos-*/SKILL.md` (31 directories; 7 added and 24 re-stamped to 1.1.0 in pass 4) |
| Vendored package | `agent-skills/packages/elmos-build-cache-staging-sota/` (v1.1.0; the v1.0.0 `elmos-build-cache-staging-recovery/` is left intact beside it, so both `./validate.sh` run in-repo) |

## Pass 2 — the seven `PARTIAL` rows

| # | Gap as stated after pass 1 | Outcome |
|---|---|---|
| 1 | E2E-001 used a stand-in generator, not real stages | **Closed for this repository.** `tests/test_e2e_real_stages.py` runs a real `javac` and a real tree-sitter-driven Java→C# translation whose output is parsed back and compared against the source's public surface. Wiring ELMOS's *model-driven* stage stays out of scope — it lives in the orchestrator. |
| 2 | PostgreSQL / S3 never seen a live service | **Closed.** PostgreSQL 16 and a live HTTP S3 endpoint, 47 + 12 executed tests. |
| 3 | Chaos injection was in-process | **Closed.** Real `SIGKILL` at 8 kill points and a real tmpfs `ENOSPC` / inode exhaustion. |
| 4 | Native adapters never ran a build tool | **Mostly closed.** Gradle, MSBuild/NuGet, Cargo, CMake+ccache, TypeScript/npm, pip and Go now run for real. Xcode/Swift, Flutter/pub and Maven Central are unavailable here and skip loudly. |
| 5 | 12 of 13 languages hashed heuristically | **Closed.** `treesitter_hash.py` gives exact extraction for all twelve non-Python languages; Python keeps `ast`. |
| 6 | HMAC signing / encryption | **Closed.** Ed25519 provenance signatures and AES-256-GCM envelope encryption, with policy refusing a symmetric signer in production. |
| 7 | Overall `NOT_CERTIFIED` | Now `CERTIFIED_IN_SANDBOX`, with the residue named in `BUILD_CACHE_HANDOFF.md` §3. |

## Pass 3 — the four that remained

| # | Gap after pass 2 | Outcome |
|---|---|---|
| 1 | macOS / Windows snapshot fixtures | **Closed for macOS's filesystem, and generalised.** The fixture now has an identical root digest on Linux/ext4 and on a real macOS APFS volume reached through the desktop bridge. A latent defect surfaced on the way: a decomposed (NFD) filename produced a different digest, which is fixed. `snapshot.portability_findings` answers the question for any repository from any host, which is what the fixtures could never do. A native Darwin run and a Windows run are still uncaptured and are named in a skip. |
| 2 | `overlay.py` had no test file | **Closed.** 36 tests, copy-on-write proven by inode and link count, the full lifecycle re-run inside a real kernel overlayfs mount. |
| 3 | Swift / Flutter / Maven toolchains | **Partly closed.** Maven's local-repository redirection is now certified against Maven itself. Swift and Flutter are not obtainable in this sandbox; for both, everything about the adapter that does not need the tool is asserted, so the residue is one specific thing and it skips with its reason printed. |
| 4 | ELMOS's own conversion stage | **Closed.** `elmos_route_stages.py` registers `engines/polyglot-route-engine` against these stage contracts. Its analyzer, IR and emitter run inside the pipeline; the emitted Java compiles and is executed against the Python original to earn `TEST_VERIFIED`; a sabotaged translation is caught. |

## Out of scope for this pass

- Calibrating `observability.DEFAULT_SLOS` against a real ELMOS workload.
- A native Darwin and a Windows snapshot capture (no such host is reachable
  from this session; one command produces each).
- Swift and Flutter builds (no toolchain, and neither vendor host is on the
  sandbox's network allowlist).

See `BUILD_CACHE_HANDOFF.md` for the ordered list of what remains.
