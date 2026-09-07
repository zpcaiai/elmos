# ETGB v1.1 release gates

The machine-readable policy is `matrices/release-gates.yaml`. Hard gates are conjunctive: a weighted score cannot override P0 semantics, data, transaction, security, authority, evidence or integrity failure.

## Non-waivable

- P0 critical Oracle pass rate = 100%;
- P0 SSER = 0;
- data corruption = 0;
- security regression/privilege expansion = 0;
- P0 transaction mismatch = 0;
- Environment/Attachment authority violations = 0;
- evidence integrity/signature/audit-chain failures = 0.

## Other release gates

- candidate/plan/Oracle/image/normalization drift = 0;
- undisclosed unsupported success = 0;
- P0 recovery failures = 0;
- budget and supply-chain failures = 0;
- performance regressions outside declared budget = 0;
- P0 flake = 0;
- required multi-seed samples complete;
- P1 weighted pass ≥ 98.5%, P2 ≥ 95%;
- approved corpus/license and 100% evidence completeness.

## Decision states

- `PROMOTE`;
- `REJECT`;
- `BLOCKED` for missing/incomplete/untrusted evidence or environment;
- `PROMOTE_WITH_WAIVER` only for explicitly waivable, scoped, expiring non-P0 failures.

No waiver is allowed for P0 SSER, data corruption, privilege escalation or evidence/authority integrity.
