# BUILD_CACHE_TASK.md

> Active task for the `elmos-build-cache-staging-recovery` skills package.
> Companion files: `BUILD_CACHE_IMPLEMENTATION_STATUS.md`,
> `BUILD_CACHE_TEST_RESULTS.md`, `BUILD_CACHE_EVIDENCE.md`,
> `BUILD_CACHE_HANDOFF.md`.

- **Started:** 2026-08-19
- **Second pass:** 2026-08-19 (closing the seven `PARTIAL` rows)
- **Agent:** Claude (Cowork, cloud session)
- **Input package:** `elmos-build-cache-staging-skills-v1.0.0` (24 skills, P0–P7)
- **Scope agreed with the user:** implement **all 24 skills** as real code,
  land it under `engines/build-cache-engine/`, install the 24 `SKILL.md` files
  into `agent-skills/runtime/`, run the package's `./validate.sh`, and record
  progress here. The second pass adds: close every gap that was only open
  because the first environment could not prove it, and re-verify.

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
| Implementation | `engines/build-cache-engine/src/elmos_build_cache/` (37 modules, 17 891 lines) |
| Tests | `engines/build-cache-engine/tests/` (30 files, 8 047 lines, 555 tests) |
| SQL migrations | `engines/build-cache-engine/migrations/{postgres,sqlite}/` (6 files) |
| JSON Schemas | `engines/build-cache-engine/schemas/` (+ packaged copy under `src/.../_data/`) |
| OpenAPI | `engines/build-cache-engine/openapi/cache-control-plane.openapi.yaml` |
| Configuration | `engines/build-cache-engine/config/elmos-cache{,.local}.yaml` |
| CLI | `elmos-cache` console script (`elmos_build_cache.cli`) |
| Skills | `agent-skills/runtime/elmos-*/SKILL.md` (24 directories, unchanged in pass 2) |
| Vendored package | `agent-skills/packages/elmos-build-cache-staging-recovery/` (intact, so `./validate.sh` runs in-repo) |

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

## Out of scope for this pass

- Wiring the pipeline into the existing ELMOS orchestrator and Skill Registry.
- Real cross-platform snapshot fixtures (macOS / Windows).
- Calibrating `observability.DEFAULT_SLOS` against a real ELMOS workload.

See `BUILD_CACHE_HANDOFF.md` for the ordered list of what remains.
