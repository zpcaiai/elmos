# Certification Matrix

| Evaluation | Blocking conditions | Core evidence |
|---|---|---|
| Requirements | Critical hallucination, omission, unresolved conflict | Source-linked requirement baseline and reviewed reference labels |
| Architecture | Unsupported quality target, premature distribution, critical threat | Architecture baseline, ADRs, tradeoff and threat evidence |
| Code | Semantic error, contract drift, invariant bypass | Behavior tests, code review, traceability |
| Runtime | Clean build/start/smoke failure | Isolated execution evidence |
| Security | Critical vulnerability, cross-tenant access, secret exposure | Adversarial tests, scanners, control mapping |
| Traceability | Broken must-have path or orphan managed artifact | Artifact Graph and release evidence |
| Regeneration | User edit loss, non-idempotence, unjustified broad diff | Multi-version regeneration benchmark |
| Parity | Material Java/Python/.NET behavior or security divergence | Common black-box scenarios |
| Scalability | Silent dropped work, superlinear cost outside declared limit | Resource and quality measurements |
| Chaos | Duplicate side effect, corrupt checkpoint, false success | Fault injection and recovery journal |

A critical failure is non-compensable and cannot be averaged out by other scores.
