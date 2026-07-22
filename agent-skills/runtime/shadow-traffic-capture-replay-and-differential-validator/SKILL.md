---
name: shadow-traffic-capture-replay-and-differential-validator
description: Capture or replay tenant-safe shadow traffic and compare primary and candidate behavior without affecting the primary path. Use before canary promotion for APIs, messages, queries, files, models, or batch jobs.
---

# Shadow Traffic Capture, Replay, and Differential Validator

## Safety first

Shadow is never the primary critical path. Require independent response capture, tenant scope, retention policy, sensitive-field redaction/tokenization/hash/synthesis/drop, and side-effect suppression by stub, shadow store, rollback, or dry-run. Compensation alone is not safe suppression.

## Workflow

1. Freeze experiment, contract version, transformations, normalization, tolerances, privacy policy, and evidence destinations.
2. Capture request hashes and approved metadata without storing forbidden payloads.
3. Execute the candidate independently; shadow failure must not alter primary success.
4. Normalize approved nondeterministic fields, then classify exact, semantic, within tolerance, expected difference, regression, not comparable, or execution failure.
5. Block canary on unsafe writes, missing privacy/tenant/retention controls, evidence gaps, regression, or shadow execution failure.

## Boundary

Shadow success is evidence for a canary gate, not production correctness and not permission to shift traffic.
