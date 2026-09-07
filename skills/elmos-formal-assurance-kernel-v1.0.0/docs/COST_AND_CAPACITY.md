# Cost, Credit and Capacity Model

## Units

Elmos reports machine wall-clock seconds for ETA. Cost accounting records:

- model token/credit reservation and consumption;
- verifier CPU-seconds and memory-seconds;
- queue and wall-clock duration;
- artifact/storage bytes;
- network bytes where permitted;
- cache savings;
- retry and reproof cost.

## Reservation

A proof plan estimates a conservative budget and reserves credit before execution. Each proof run has an idempotent usage event. Finalization reconciles reserved, consumed and refundable amounts.

## Scheduling

P0 release/drift work has priority, but an account still has at most three top-level active tasks. Large plans execute internal independent obligations in parallel subject to global and adapter quotas.

## ETA calibration

Track predicted versus actual wall-clock by engine, property kind, formula size, semantic profile and cache state. Publish confidence intervals. Do not convert machine ETA into artificial human-day estimates.

## Cost controls

- exact cache keys and incremental reproof;
- obligation decomposition;
- early structural checks before expensive proof;
- portfolio time slicing;
- stop after decisive counterexample;
- proof-strength policy by risk;
- artifact compression and retention tiers.
