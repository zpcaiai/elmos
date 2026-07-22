# Batch 30 Framework Pack Quality Gates

## Gate F30-A — Manifest, ownership, and exact tuple

- pack manifest validates
- source and target framework/runtime/provider versions are exact
- mode and direction are explicit
- accountable owner and maintenance owner exist
- review date and lifecycle state exist
- no floating `latest` versions or mutable image tags

## Gate F30-B — Source runtime fingerprint

- static discovery runs
- runtime or build-time discovery runs where required
- declared-only, active, conditional, generated, test-only, and unknown facts are distinguished
- critical source fingerprint coverage meets the pack threshold
- source evidence respects secret and source-egress policy

## Gate F30-C — Framework Contract Model

- required capabilities are represented in versioned FCM contracts
- source trace and confidence exist
- ordering, defaults, conditions, lifecycle, and provider behavior are explicit
- critical contract coverage meets the pack threshold
- no silent framework drops

## Gate F30-D — Target profile and real execution

- exact target profile and provider locks exist
- target project builds with the real toolchain
- target application or worker starts with the real runtime
- startup health and shutdown behavior pass
- added dependencies have SBOM/license/security evidence

## Gate F30-E — P0 contract safety

- web/request/error contracts pass where applicable
- DI and lifecycle contracts pass
- configuration precedence and validation pass
- authentication and authorization regressions are zero
- persistence, transaction, and concurrency regressions are zero
- message/cache/scheduler duplicate or loss regressions are zero
- test-integrity violations are zero

## Gate F30-F — Independent evidence

- holdout corpus is physically separate
- representative repository corpus is non-empty
- holdout cases were not used to author rules
- source maps meet the declared threshold
- critical unknowns and P0 behavior regressions are zero for certified scope

## Gate F30-G — Lifecycle, maintainability, and coexistence

- version/lifecycle matrix is current
- compatibility/runtime/coexistence components have owners, budgets, SLOs, and exit plans
- customer-owned code is protected
- rollback or transition plan exists
- maintenance and support responsibility is funded

## Certification outcomes

- `certified`: every required gate passes for the declared exact tuple and scope
- `limited`: useful and safe subset with explicit conditions and blockers
- `experimental`: implementation exists but independent evidence is insufficient
- `blocked`: a critical correctness, security, data, lifecycle, or maintenance requirement fails
