# Operations Guide

## Daily operations

Monitor queue delay, proof wall-clock, cache hit, unknown ratio, counterexample ratio, evidence age, sandbox failures, credit reservation failures and gate denial reasons.

## Queue priority

1. production P0 drift revalidation;
2. release-blocking P0 proofs;
3. active customer conversion;
4. P1/P2 proofs;
5. exploratory or background proof strengthening.

Priority never bypasses per-account concurrency or credit limits.

## Solver incidents

- Crash/malformed output: classify as infrastructure failure; preserve raw logs.
- Timeout: keep `UNKNOWN_TIMEOUT`; split obligations, add invariants, or select a compatible engine.
- Memory exhaustion: keep `UNKNOWN_RESOURCE_LIMIT`; reduce model or increase approved resource class.
- Solver disagreement: mark conflict, stop publication, run independent checker and review semantic translation.
- Counterexample: reproduce before repair; generate permanent regression fixture.

## Database incidents

Proof metadata is authoritative in PostgreSQL. Object artifacts are authoritative only when a committed row and matching digest exist. Use transactional outbox for event publication. Do not infer success from orphaned object-store files.

## Backup and restore

Back up PostgreSQL, object metadata, KMS references and release manifests. Perform restore drills that verify proof-artifact hashes and latest gate decisions. Legal-hold artifacts require separate retention controls.

## Capacity

Capacity planning uses machine wall-clock, CPU-seconds, memory-seconds, artifact bytes and solver-specific historical percentiles. Never convert machine ETA to developer days in the product API.
