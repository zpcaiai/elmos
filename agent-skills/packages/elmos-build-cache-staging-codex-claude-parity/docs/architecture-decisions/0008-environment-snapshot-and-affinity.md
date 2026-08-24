# ADR-0008: Cache immutable environments and route by compatible locality

Status: accepted

## Decision

ELMOS snapshots base/toolchain/dependency/index layers under a precise key and exposes snapshot/local-CAS/provider-prefix inventory to a scheduler. Compatibility and authorization are hard filters; locality is a soft score with bounded-load and fairness escape.

## Consequences

- Repeated setup and dependency installation can be avoided.
- Wrong-shard and cold-worker misses become diagnosable.
- Secrets remain mounted after restore and never enter reusable layers.
- Worker failure may reduce hit rate but cannot affect durable run state.
