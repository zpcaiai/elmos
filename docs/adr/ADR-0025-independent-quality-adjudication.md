# ADR-0025: Independent baseline and migrated quality adjudication

- Status: Accepted
- Date: 2026-07-21

## Decision

The validation module is framework-free and has no dependency on recipe transformation, agent repair, workers or gateways. Baseline and migrated revisions run in separate workspace and environment identities with comparable pinned tools, immutable container image digests and fixtures. Testcontainers reuse is forbidden for adjudication because its own documentation describes reusable containers as experimental and unsuitable for CI.

Every domain reports `PASS`, `PASS_WITH_WARNINGS`, `FAIL`, `MISSING` or `INCONCLUSIVE`. Not run and missing evidence never become pass. A stable pre-existing baseline failure is recorded rather than misattributed to migration, while a new failure, skipped test, missing test identity, contract break, schema tightening, transaction behavior change or stable severe performance regression blocks quality.

The final decision is produced only by a versioned policy over required domains, hard-fail codes, evidence references and confidence. Human exceptions are separate records and cannot rewrite observations.

## Consequences

Docker-backed environment validation is an external gate on hosts without an approved image and working daemon. Unit tests validate comparison and aggregation policy without claiming container execution occurred.
