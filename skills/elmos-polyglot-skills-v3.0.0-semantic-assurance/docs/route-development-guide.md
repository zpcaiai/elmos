# Route Development Guide

## Do not start with text generation

A new route begins with source discovery, native parser support, behavior contracts, target profile, and a verification corpus. A prompt that says “convert X to Y” is not a route implementation.

## Minimum route implementation

1. Source and target adapter smoke builds.
2. At least one representative source fixture with immutable baseline.
3. Project, Semantic, and Framework IR coverage report.
4. Route-specific semantic mapping and loss taxonomy.
5. Deterministic rules for high-volume, low-ambiguity changes.
6. Bounded patch tasks for residual changes.
7. Native target build.
8. Contract and differential behavior tests.
9. Data, performance, and security checks where applicable.
10. Rollback or approved non-reversibility.
11. Evidence bundle and bounded readiness decision.

## Route maturity

```text
R0 Profile only
R1 Parse and inventory
R2 Compile representative target
R3 Contract-equivalent sample
R4 Data/performance/security validated sample
R5 Repeatable cohort
R6 Production workload verified
```

Maturity is route-, version-, framework-, and workload-specific. It is not inherited merely because both adapters exist.

## Adding a route

Copy `templates/route-profile.yaml`, register it in `route-registry.yaml`, add route-specific fixtures, tests, and acceptance budgets, then run `./validate.sh`.
