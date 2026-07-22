# Batch 9 behavioral equivalence and Golden Master validation

`modules/behavior-equivalence` implements the fail-closed Batch 9 control plane from ADR-0038.
It receives Batch 8 R-D modules, creates a comparable source-target run contract, consumes external
OBM observations and Oracle results, detects unstable differences, routes regressions back to
Batch 8 and evaluates module gates E-A through E-E.

## Implemented offline guarantees

- Immutable source/target Snapshot and runtime-role binding with separate mutable-resource checks.
- Explicit configuration, feature flag, locale/timezone, database/cache/message, external response,
  virtual clock, random source, clean environment, production-access and secret alignment evidence.
- Versioned scenarios, blocking-obligation mapping, required observation-point coverage and trusted
  source Golden admission for every critical scenario.
- OBM records for return, HTTP, database state/write trace, messages, files/object storage, cache,
  external calls, exceptions, log/audit/metrics, resource lifecycle and concurrency.
- Required multi-Oracle enforcement; a failed, unknown or unexecuted required Oracle cannot pass.
- Scoped normalization, tolerance and approved-change validation with protected security, money,
  tenant, status/count, transaction and audit semantics.
- Agent non-adjudication, source-bug separation, immutable comparison evidence and Batch 8 feedback.
- Matching clean-run fingerprints, flaky exclusion and per-module E-A through E-E gates.
- `eligible_for_cutover=false` as a model invariant for all Batch 9 reports.
- Full artifact directory, 17 reports, YAML/JSON and Zstandard streams, append-only writes and
  symbolic-link rejection outside both repositories.

The 35 Skills under `agent-skills/behavioral-equivalence` implement Skills 166–200. Eleven JSON
Schemas under `contracts/behavior-equivalence-schema` define the run, OBM, observation points,
scenarios, alignment, normalization, Golden, comparisons, root-cause feedback, tolerance/approved
change and conformance protocols.

## Gate interpretation

- E-A proves comparable, isolated and controlled execution inputs and observation readiness.
- E-B adds public HTTP, security, validation and failure-contract equivalence.
- E-C adds database, transaction, message, file and audit side-effect equivalence.
- E-D requires all critical scenarios, at least 0.98 required-scenario acceptance, no unapproved
  change/open blocking obligation/critical unknown/flaky difference, strict security-money-
  transaction behavior and at least two matching clean runs.
- E-E adds at least 0.995 required/observation/trace coverage, property and metamorphic rates at
  least 0.99 and flaky rate at most 0.005.

Approved changes can be acceptable for a scoped ordinary contract while remaining distinct from
strict equivalence. Security, money and transaction scenarios must remain strictly equivalent for
E-D. A module at E-D/E-E may enter Batch 10 production hardening; it is not approved for cutover,
production traffic, source retirement or decommissioning.

## Required external authorities

1. Independent source and target runtimes with pinned images/versions, denied production access,
   separate databases, brokers, caches, storage, namespaces, identities and schedulers.
2. Native application clock/random adapters, state seed/snapshot tools and sanitized record/replay.
3. Non-perturbing collectors for HTTP, transaction/write traces, messages/acks, files/storage,
   cache, external calls, errors, audit/security events, resources and concurrency.
4. Domain-aware Oracles for JSON presence/null/order/Decimal, logical database mapping,
   transaction atomicity, causal messages, archive/binary content, cache TTL, logical errors and audit.
5. Fault and concurrency harnesses, property generators/shrinkers and reviewed metamorphic relations.
6. Human review for Golden changes, conditional normalization, tolerances and approved differences.
7. Privacy/tokenization, secret scanning, access control, retention and evidence attestation.

## Evidence boundary

The 16 module tests use injected deterministic authorities. They prove orchestration, validation,
Gate and artifact safety, not that a customer source and target were executed. No real source or
target runtime, database, broker, object store, traffic stream, credential, production sample,
external provider or human approval was configured here. Those states remain external and
`NOT_RUN` until supplied by an approved deployment.

## Local verification

```bash
mvn -pl modules/behavior-equivalence -am test
python3 /Users/stephen/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  agent-skills/behavioral-equivalence/behavioral-equivalence-orchestrator
jq empty contracts/behavior-equivalence-schema/*.json
```
