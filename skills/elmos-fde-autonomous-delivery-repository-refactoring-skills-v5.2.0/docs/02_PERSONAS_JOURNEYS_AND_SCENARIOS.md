# 02 — Personas, Journeys and Scenario Coverage

The machine-readable scenario catalog contains **279** cases: {'positive-or-edge': 135, 'negative-trigger': 114, 'system-edge': 30}.

## Critical journeys

1. New customer with incomplete documents and conflicting stakeholder descriptions.
2. Legacy monorepo that cannot build because artifact registries and SDKs are missing.
3. Mixed Java/TypeScript/SQL system with runtime reflection and generated code.
4. Security-sensitive customer requiring private deployment, data residency and CMK.
5. Production incident requiring rapid diagnosis without unsafe edits.
6. Repository-wide refactor requiring behavior preservation and reversible commits.
7. Cross-language or framework migration with compiler-native differential evidence.
8. Database schema/routine/data migration with CDC and reconciliation.
9. Multi-repository portfolio constrained by budget, staffing and maintenance windows.
10. Completed pilot with weak adoption despite acceptable technical metrics.

## Required scenario classes

- normal, partial-input, conflicting-input, stale-input and inaccessible-input;
- unsupported language/framework/database and dynamic behavior;
- permissions denied, credential unavailable, rate limited and network isolated;
- timeout, cancellation, worker loss, retry, duplicate event and stale executor;
- unexpected files, generated code drift, dirty workspace and submodule mismatch;
- false positive, false negative, weak oracle and contradictory analyzer results;
- data loss, partial migration, side-effect duplication and rollback failure;
- user rejection, adoption drop, scope expansion, procurement delay and ownership gap.

See `catalog/scenarios.json`, `catalog/scenarios.csv` and `evals/`.
