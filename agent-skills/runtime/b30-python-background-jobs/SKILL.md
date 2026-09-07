---
name: b30-python-background-jobs
description: "Implement or certify Celery, RQ, and Python background-job migration, including task registration, serialization, queues, routing, retries, acknowledgement, schedules, result backends, groups/chords, idempotency, worker lifecycle, and target provider profiles."
---

## Operating mode

Work in the repository. Inspect existing Batch 20-29 modules, contracts, build commands, framework packs, and tests before editing. Implement the smallest production-shaped vertical slice that satisfies this skill; do not stop at a design document when code, manifests, and executable tests can be added.

Read these shared contracts first:

- `../../../docs/batch30/IMPLEMENTATION_CONTRACT.md`
- `../../../docs/batch30/QUALITY_GATES.md`
- `../../../docs/batch30/REPOSITORY_LAYOUT.md`
- `../../../docs/batch30/VERSION_POLICY.md`

Use the supplied helpers where applicable:

- `python3 scripts/batch30/scaffold_framework_pack.py ...`
- `python3 scripts/batch30/validate_framework_pack.py ...`
- `python3 scripts/batch30/run_framework_gate.py ...`

## Global constraints

- Treat every framework migration pack as directional and version-specific. Reverse migration and version upgrade are separate packs.
- Extract runtime behavior into the framework-neutral Framework Contract Model before generating target code. Do not implement annotation-name substitution as the migration architecture.
- Invoke real source and target build/runtime tools. A generated project that only parses is not evidence of support.
- Preserve authentication, authorization, transaction, persistence, message delivery, configuration precedence, validation, lifecycle, and error contracts.
- Keep development, holdout, and representative-repository corpora physically separate. Do not author rules from holdout cases.
- Prefer deterministic mappings and certified adapters. Model-generated output is a candidate and must pass the same build, contract, behavior, security, and test-integrity gates.
- Record unsupported, conditional, and unknown behavior explicitly. Never hide it with TODOs, permissive stubs, broad exception swallowing, disabled security, or weakened tests.
- Record exact framework/runtime/provider versions, source and target commits, recipe digest, model/prompt versions, toolchain digests, and evidence references.
- Fix repeated failures in the fingerprint, contract model, recipe, adapter, or generator instead of patching many generated files.
- Run the narrowest relevant tests first, then the independent holdout suite and framework certification gate before making release claims.


## Skill 1176: Celery, RQ, and Python background-job migration

Migrate Python background task systems while preserving delivery, retry, scheduling, orchestration, result, idempotency, concurrency, and operational contracts.

## Use this skill when

- A Python service uses Celery, RQ, Beat, result backends, or custom workers.
- Background jobs are moving to another framework, broker, scheduler, or language runtime.
- An existing framework migration ignores non-HTTP workloads.

## Framework-specific risks and invariants

- Ack timing, visibility timeout, late ack, retry, redelivery, worker crash, prefetch, and broker behavior determine duplicate/loss risk.
- Serialization, routing, headers, countdown/ETA, periodic schedules, and result backends are part of the contract.
- Chains, groups, chords, callbacks, and errbacks are distributed workflows, not ordinary function calls.
- Worker process/thread/greenlet behavior affects context, resources, time limits, and shutdown.

## Workflow

1. Lock framework, broker, result backend, serializer, scheduler, worker pool, and target provider versions.
2. Fingerprint registered tasks, signatures, queues/routes, serialization, ack/retry/time-limit policies, periodic schedules, workflows, results, signals, and worker lifecycle.
3. Extract message, scheduler, workflow, idempotency, timeout, cancellation, and operational contracts.
4. Select a target worker/broker/scheduler profile and classify each task/workflow as direct, adapter, orchestrated workflow, retained runtime, or blocked.
5. Generate one complete producer-worker-retry/result-or-side-effect flow with observability and tests.
6. Run source and target broker-backed tests for delivery, duplicate, crash-before/after-ack, retry, dead-letter/failure, schedule, shutdown, and idempotency.
7. Run holdout cases for chains/groups/chords, inheritance, custom serializers, signals, dynamic routing, and result backends.
8. Publish operational, coexistence, rollback, and retirement guidance.

## Required repository outputs

- `framework-packs/celery-rq-to-<target>/`
- Task topology and worker runtime fingerprint
- Message/workflow/scheduler contracts
- Target worker/provider adapters and recipes
- Fault and duplicate-delivery corpus
- Operational/certification evidence

## Verification

- Run real source and target brokers/workers in isolated environments.
- Verify ack, retry, duplicate, crash, schedule, timeout, result, and shutdown behavior.
- Verify no production messages or real external side effects occur.
- Run holdout and the framework gate.

## Stop and escalate when

- Delivery semantics are reduced to a normal function call.
- Non-idempotent tasks are retried without strategy.
- Complex workflows are flattened without behavior tests.
- Broker/result-backend versions or policies are unknown.

## Definition of done

The background-job pack captures task and workflow topology, migrates a real broker-backed flow, passes delivery/retry/failure/idempotency/holdout tests, and documents operational and coexistence boundaries.
