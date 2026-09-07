# Batch 8 build, static-analysis and test repair loop

`modules/repair-orchestration` now implements the evidence-bound Batch 8 control plane described by
ADR-0036. It converts a Batch 7-admitted target Snapshot into a polyglot execution matrix, consumes
external build/test evidence, normalizes and attributes failures, controls deterministic/Agent
repairs, validates atomic patches and decides a finite terminal outcome.

## Implemented offline guarantees

- Java, Python, C#, JavaScript and TypeScript minimum-sufficient matrix and pinned command records.
- Secret-redacted Diagnostic protocol with stable fingerprints, native codes and raw evidence refs.
- Root-cause clustering, source/migration/environment/test attribution and confidence preservation.
- One-cluster/one-plan repair planning with deterministic-first Agent fallback.
- File/declaration/hash/size/dependency/manual-region/public-API/security/transaction/test/suppress/
  dynamic policy checks.
- Atomic apply/rollback authority contract and affected-scope plus full-regression sequencing.
- Effectiveness, repeated-patch, oscillation, three-round no-progress and Agent resource budgets.
- Zero-test false-green prevention, source-existing failure exclusion and required-test stability.
- Matching clean-run convergence, per-module R-A through R-D gates and optional R-E automation candidates.
- YAML/JSON/Zstandard artifacts, complete report layout and symlink-safe writes outside the target.

The 32 Skills under `agent-skills/build-test-feedback` implement Skills 134–165. Nine JSON Schemas
under `contracts/repair-loop-schema` define the manifest, matrix, Diagnostic, Cluster, attribution,
repair plan, structured patch, stop decision and Batch 8 conformance report.

## Required live authorities

1. Rootless, resource-limited build/test sandboxes with denied production access, approved registry
   allowlists, immutable images, short-lived test credentials and process-tree cleanup.
2. Native wrapper/tool execution for Maven/Gradle, Python/uv, dotnet/MSBuild and Node package
   managers plus the configured analyzers and test frameworks.
3. Deterministic repair recipes with fixtures/idempotence and target-language AST/CST/LST emitters.
4. Bounded Agent providers operating only on an editing Snapshot without SCM, secret, production,
   host-process or validation-workspace authority.
5. Independent Patch inspection that derives actual scope, generated/manual boundaries, contract,
   test, dependency, Suppress and Dynamic changes instead of trusting Agent declarations.
6. Transactional candidate-worktree/Snapshot apply and rollback with generated/manual boundaries.
7. Independent clean validation environments and approved ephemeral databases, brokers, caches and
   external-service fakes.

## Evidence boundary

Unit tests use injected deterministic authorities. They prove control-flow, policy and fail-closed
behavior, not that a real target repository restored dependencies, compiled, passed analyzers or
tests, or was repaired by a live Agent. The current repository test suite is evidence about ELMOS
itself, not a migrated customer target. R-D admits a module to Batch 9 only.

## Local verification

```bash
mvn -pl modules/repair-orchestration -am test
python3 /Users/stephen/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  agent-skills/build-test-feedback/repair-loop-orchestrator
jq empty contracts/repair-loop-schema/*.json
```
