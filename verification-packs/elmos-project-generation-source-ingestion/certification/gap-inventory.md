# Gap inventory

## Closed with local executable evidence

- Exact source and test files are repository-bound by byte count and SHA-256.
- All declared lifecycle transitions and the local P0 boundary contract are exercised.
- Every declared evidence reference and verification contract is content-bound.
- Seeded property, metamorphic, structured-fuzz, two targeted mutation-negative-control,
  security, counterexample replay, local holdout, and engineering-workload checks pass.

## Certification blockers requiring authorized external evidence

- `NOT_RUN`: independent verifier replay, independent P0 oracle, and approvals.
- `NOT_RUN`: controlled public DNS-rebinding and redirect-chain security campaign.
- `NOT_RUN`: independently supplied holdout and production-derived representative workload corpus.

## Explicit non-required limitation

- External solver or symbolic execution is `NOT_RUN`; the profile does not require it
  for this parser/security claim and the 256-case campaign is not a universal proof.
- The two-mutant score is an explicit negative control, not a whole-program mutation score.
