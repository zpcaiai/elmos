# Elmos Runtime and Billing Formal Golden Route

This Golden Route defines the minimum repeatable path for commercial certification of `platform`.

## Critical properties

- top-level active tasks per account never exceed three
- stale fencing tokens cannot commit state or evidence
- terminal states do not regress
- usage events are charged at most once and balances never go negative
- pause/resume/cancel/recovery do not repeat committed side effects

## Certification conditions

- network partition
- worker crash
- database failover
- event duplication/reordering
- E1-E5 complete

A successful package validation is not an E5 certification. E5 requires real repositories/environments, exact toolchain pins, failure injection and signed evidence.
