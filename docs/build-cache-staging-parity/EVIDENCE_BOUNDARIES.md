# Build-cache parity v1.2 evidence boundaries

## Status vocabulary

| State | Meaning here |
| --- | --- |
| `PASS` | The named local command executed and its scoped assertion passed |
| `NOT_RUN` | Required execution evidence does not exist; never equivalent to pass |
| `READY_FOR_EXTERNAL_GATE` | Maximum local readiness, only after all required local evidence is bound |
| `NOT_CERTIFIED` | No authorized external certification exists |

## What local evidence establishes

- The pinned archive inventory/checksums and delta-aware 42-Skill installation.
- Byte-identical installed Skills across four roots without deleting unrelated
  files.
- Typed contracts, Schema validation and the documented production OpenAPI
  overlay.
- SQLite migrations and local durable repository behavior.
- Pure/local behavior for prompt layout, ledger/compaction, environment CAS,
  affinity, coordination, diagnostics, parity evaluation, tuning and rollback.
- Local API/CLI wiring and real pipeline Action Cache observation.
- Fail-closed behavior when evidence, identity, authorization, trust, content
  integrity or independent verification is missing.

This is engineering evidence. It does not establish vendor or production
behavior.

## What remains `NOT_RUN`

| Domain | Required missing evidence |
| --- | --- |
| PostgreSQL | Disposable live application of v1.2 DDL plus repository, concurrency, reopen and idempotency tests |
| Providers | Exact provider/SDK/API/model/effort/tool profile runs and provider-reported cached-token accounting |
| Environment | Exact image/bootstrap/lockfile/toolchain/platform builds, runner warm inventory, restore timing, corruption and rebuild traces |
| Context | Representative long sessions, compaction warmup, restart and branch/snapshot behavior |
| Fleet | Real scheduler candidates, load, trust domains, failover, fairness and wrong-shard accounting |
| Parity | Independent execution of all 20 scenarios over separate corpora with immutable raw evidence and replay |
| Operations | Shadow/canary/progressive rollout, false-hit rollback, incident and recovery evidence |
| Production | Customer/workload outcome, production scale, security review and external certification |

## Prohibited inferences

- A provider prompt-prefix hit is not exact model-output reuse.
- A file, layer, row or manifest existing is not proof of completion or reuse.
- SQLite success does not prove PostgreSQL behavior.
- Local CAS bytes do not prove remote/distributed CAS or a runner's warm image.
- Synthetic/local scenarios do not prove Codex/Claude equivalence.
- A benchmark harness, Schema, signed fixture or high local hit ratio is not
  certification.
- `UNKNOWN`, `BLOCKED`, `INCONCLUSIVE`, missing or `NOT_RUN` never passes.
- Local autotuning may change performance knobs only; it cannot weaken
  ActionKey identity, validation, tenancy, provenance or publication rules.

## Current decision

The v1.2 implementation is present and locally testable. Real provider,
environment, PostgreSQL, representative-corpus, field-rollout and independent
verification evidence is absent. The current decision is therefore
`NOT_CERTIFIED`, with external evidence `NOT_RUN`. None of the package's parity
thresholds is claimed as achieved.
