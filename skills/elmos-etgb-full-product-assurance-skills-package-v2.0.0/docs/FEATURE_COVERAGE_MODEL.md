# Feature Coverage Model

## Source of truth

`matrices/feature-registry.yaml` contains **1,452 product features**. Each entry has a stable ID, domain, priority, owner, required Adapter and release policy. `matrices/full-product.yaml` defines contexts, variants and Oracles. Materialization expands these into **23,232** direct cases.

## Traceability chain

```text
Implemented surface
  → Feature ID
  → Matrix capability
  → Context × variant concrete cases
  → Production Adapter and exact environment
  → One or more independent Oracles
  → Raw and normalized evidence
  → Candidate-specific release gate
```

The `etgb feature-coverage` command checks exact case cardinality, required Adapter identity, P0 variant completeness, unknown capabilities and registry drift. Its current report is `reports/FEATURE_COVERAGE.json`.

## Discovery inputs

Production CI should discover and reconcile:

- public/private API operations and SDK methods;
- browser routes, interactive actions and accessibility states;
- commands, background jobs and schedulers;
- event topics/types and webhook operations;
- database migrations and data lifecycle jobs;
- feature flags, entitlements, quotas and billing meters;
- model providers, tools, MCP/A2A capabilities and Agent routes;
- admin/support/security operations;
- export, document, diagram and artifact formats;
- deployment modes, observability signals and recovery procedures.

## Gap classes

| Gap | Release effect |
|---|---|
| `UNDECLARED_FEATURE` | block |
| `NO_CASE` | block |
| `NO_ADAPTER` | block |
| `NO_ORACLE` | block |
| `UNAVAILABLE` | block in release/golden |
| `STALE_EVIDENCE` | block |
| `MISSING_JOURNEY` | block when feature participates in critical workflow |
| `MISSING_CONTROL` | block for mandatory profile |

## Priority policy

- P0: all contexts and four variants; 100% critical Oracle pass; no waiver for security, data, tenant or finance invariants.
- P1: all declared contexts/variants with ≥98.5% weighted pass, except mandatory controls remain must-pass.
- P2: ≥95% weighted pass or explicit manual product acceptance.

## Non-claim

Coverage is complete for the versioned registry, not for unknown future functionality. The registry must be regenerated and reviewed whenever implementation discovery finds a new surface.
