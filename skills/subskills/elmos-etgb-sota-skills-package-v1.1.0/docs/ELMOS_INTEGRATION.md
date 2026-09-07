# Integrating ETGB v1.1 into Elmos

## 1. Merge order

1. Apply PostgreSQL schema/RLS from `integrations/postgres/`.
2. Register the 24 Skills from `skills/manifest.yaml`.
3. Implement Environment/Attachment authority and tool-boundary enforcement.
4. Implement the Harness adapter contract for each business line.
5. Wire durable workflow/state/checkpoint/outbox.
6. Wire evidence object storage, signing, redaction and retention.
7. Wire token/credit usage ledger, prepaid reservation and machine ETA.
8. Add OpenAPI/AsyncAPI endpoints/events and OTel attributes.
9. Run all 100 cross-cutting scenario families against production infrastructure.
10. Enable release certification only after corpus/license and evidence gates pass.

## 2. Core entities

Use the supplied PostgreSQL migration for:

- benchmark suite/case/version and capability coverage;
- corpus snapshot and immutable release candidate;
- immutable run plan and stable shards;
- Environment authority, run, case run, transition and checkpoint;
- Oracle result and evidence artifact/seal;
- budget reservation and usage ledger;
- gate result/waiver;
- failure cluster/regression link;
- idempotency and transactional outbox.

Every record carries `tenant_id`; forced RLS is the baseline isolation control.

## 3. Harness adapters

Implement:

```text
prepare(case, environment)
baseline(case)
transform_or_generate(case)
build(case)
validate(case)
score(case)
publish(case)
compensate(case)
cleanup(case)
```

Each call receives owner/fence/idempotency/candidate/plan/checkpoint context. A stale worker cannot mutate, publish, charge or perform external side effects.

## 4. Authority domains

Create at least two Environments per case:

- transform/generation: source/public tests + writable target, no hidden tests;
- validation: read-only target + hidden-test execution + evidence staging.

Evidence and release actions may use additional narrower Environments.

## 5. Cache keys

Include tenant/public scope, input/source digest, target stack, model revision, Prompt/Skill/rules/toolchain/image, candidate/plan/case/Oracle/normalization versions, seed and security policy. Any semantic/policy/hidden-test change invalidates reuse.

## 6. Workflow and recovery

Use Temporal or equivalent durable workflow. Persist transition/checkpoint and outbox transactionally. Pause at safe points; resume only after all digests match and a new fence is acquired. Cancellation compensates promised effects and reconciles actual usage.

## 7. Cost and ETA

Before admission, enforce the account's default three-active-task limit, reserve prepaid tokens/credits and compute p50/p90 Elmos machine wall-clock. Post phase usage idempotently and close/reconcile on every terminal state.

## 8. Evidence

Persist raw evidence before normalization, redact/quarantine, content-address by SHA-256, append chain-of-custody events, seal/sign the manifest and verify it before gate evaluation.

## 9. Dashboard

Show coverage, pass, SSER, HIR, unsupported, unavailable, flake, mutation, recovery, evidence, authority, cost and machine wall-clock. Drill down to candidate/plan/case/phase/Oracle/first difference and failure cluster.

## 10. Release

`etgb gate` is a reference evaluator. Production release evaluates the same `matrices/release-gates.yaml` against complete persisted metrics. Missing metrics, license review or evidence produce `BLOCKED`, not pass.
