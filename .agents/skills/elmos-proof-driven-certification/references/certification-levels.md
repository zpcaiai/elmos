# Certification Levels E0–E5

These are policy baselines, not hard-coded application logic. OPA bundles should define the actual requirements per business line/version.

| Level | Baseline meaning |
|---|---|
| E0 | Immutable subject + trusted build integrity |
| E1 | E0 + deterministic public verification |
| E2 | E1 + protected hidden tests + contract verification |
| E3 | E2 + integration/E2E + mutation + independent semantic audit |
| E4 | E3 + security/sabotage + strong workload identity + cryptographic provenance + reproducibility controls |
| E5 | E4 + independent re-execution/multi-runner evidence + strongest supply-chain controls + formal verification where applicable |

## Important

- Do not let Builder choose a weaker level after failure unless product policy explicitly allows downgrade and records it.
- Every certification records the exact policy bundle digest and level.
- A higher level does not mean one universal mutation/coverage threshold; use business-line and risk-specific policy.
- `UNKNOWN` semantic claims on required E3+ requirements should normally deny certification.
