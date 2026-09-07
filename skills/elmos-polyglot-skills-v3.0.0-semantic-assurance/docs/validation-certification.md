# Validation and Certification

## Gate states

- `not-run`: no current execution evidence.
- `blocked`: prerequisite or environment prevented execution.
- `fail`: executed evidence violates criteria.
- `waived`: authorized, scoped, expiring exception with compensating control.
- `pass`: current evidence satisfies criteria.

## Evidence layers

1. Static parse and schema validation.
2. Clean native build.
3. Unit and focused integration tests.
4. Contract and compatibility tests.
5. Differential behavior and golden masters.
6. Data equivalence and transaction behavior.
7. Performance and capacity budgets.
8. Security and supply-chain validation.
9. Deployment, rollback, recovery, and operability.
10. Production-like or controlled canary evidence.

## Suggested readiness levels

| Level | Meaning |
|---|---|
| E0 | Profile/package exists; not executed |
| E1 | Source and target parse/build evidence |
| E2 | Unit and contract tests |
| E3 | Integration and differential behavior |
| E4 | Data, performance, security, rollback |
| E5 | Bounded production migration readiness |

A certificate is valid only for exact source snapshot, target artifacts, environment, policies, and time. It is not a universal claim about a language pair.
