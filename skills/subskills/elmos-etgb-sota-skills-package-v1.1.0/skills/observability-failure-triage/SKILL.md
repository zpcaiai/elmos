---
name: observability-failure-triage
description: Instrument ETGB with bounded-cardinality telemetry, classify failures, cluster regressions, detect flakes and expose evidence-linked operational dashboards.
---

# Observability and Failure Triage

## Instrumentation

Create one trace spanning plan, run, shard, case and phase. Attach tenant/project/task/run/case/capability, candidate/plan/environment/authority digests, fencing token, phase, attempt, seed, model usage and failure class. Follow `integrations/otel/semantic-conventions.yaml`.

Do not put source paths, Prompts, hidden-test names, evidence URIs, exception messages or user data into metric labels. High-cardinality values belong in access-controlled traces/logs.

## Required metrics

- queue/start/phase/end machine wall-clock;
- throughput, active shards and account concurrency;
- pass, SSER, HIR, unsupported and unavailable;
- Oracle mismatch class and first-difference type;
- checkpoint/resume/compensation outcome;
- tokens, credits, cache hits and budget ratio;
- evidence completeness/integrity;
- flake and multi-seed instability;
- mutation survivors and fuzz discoveries.

## Triage workflow

1. Preserve raw evidence.
2. Separate source-baseline, infrastructure, product, Oracle/test and policy failures.
3. Normalize volatile paths, IDs and numbers in error signatures.
4. Cluster by business line, capability, first difference and stack signature.
5. Link clusters to prior incidents, candidate regression and owner.
6. Quarantine suspected Oracle defects; never auto-classify them as product passes.
7. Produce a minimal reproduction and determine retry eligibility.

## Flake detection

Repeat deterministic cases under the same candidate/environment. Distinguish test flake, environmental nondeterminism and product nondeterminism. P0 flake is a release blocker until classified and fixed or the test is formally quarantined with replacement coverage.

## Implementation

Use `etgb/triage.py`, `etgb stability`, OTel conventions and PostgreSQL failure-cluster tables.

## Dashboard

Provide business-line summary and drill-down to case, phase, first difference, evidence and linked incident. Never show only a global average that conceals P0 failures.
