# ADR-0009: Certify defined workloads; never claim a universal vendor-equivalent hit rate

Status: accepted

## Decision

ELMOS uses hard cache parity SLOs on a pinned corpus and live declared cohorts. Release language must distinguish target, certified benchmark result, and production observation. Any false hit blocks certification regardless of performance.

## Consequences

- Claims remain honest despite provider/model/workload variability.
- Cold starts and legitimate invalidations remain visible.
- The release process requires reproducible reports, worst-cohort floors, and certificate expiry after material change.
