# ADR-0017: Evidence-bound migration planning

Status: Accepted

## Decision

Batch 4 planning is a deterministic function of an immutable health report, organization target policy, and a versioned compatibility matrix. The plan is a topologically ordered DAG with stable step IDs, bounded waves, explicit evidence requirements, approval gates and immutable artifact hashes.

Risk and automation scores expose their factors. Human effort is a minimum/likely/maximum range with confidence and assumptions; it is not a commitment or a single-point estimate. Unknown Java, build, vulnerability or source evidence blocks execution rather than lowering risk.

