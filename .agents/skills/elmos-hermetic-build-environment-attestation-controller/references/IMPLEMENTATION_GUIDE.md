# Implementation Guide — Hermetic Build Environment Attestation Controller

## Purpose

Attest builder image, kernel, toolchain, network policy, inputs, identity and isolation so clean-room results can be trusted beyond a build log.

## Required vertical slice

A conforming first implementation must execute one real, exact-version vertical slice through:

1. API command and idempotency validation;
2. PostgreSQL run/event/outbox persistence with tenant policy;
3. K7 authority, sandbox, lease and fencing acquisition;
4. the Skill-specific native operation;
5. at least one positive and one negative native fixture;
6. independent proof/evidence production;
7. K8 blocked-or-certified decision;
8. pause/resume and worker-loss recovery;
9. machine wall-clock and cost reporting;
10. safe uninstall/rollback or compensating action.

## Skill-specific work packages

1. Measure builder image and toolchain
2. Bind workload identity and execution epoch
3. Verify network/filesystem isolation
4. Compare evidence with approved reference values
5. Reject stale or unverifiable attestation

## Native acceptance corpus

- `ELMOS_HERMETIC_BUILD_ENVIRONMENT_ATTESTATION_CONTROLLER-01` — known-good builder
- `ELMOS_HERMETIC_BUILD_ENVIRONMENT_ATTESTATION_CONTROLLER-02` — modified image rejected
- `ELMOS_HERMETIC_BUILD_ENVIRONMENT_ATTESTATION_CONTROLLER-03` — unauthorized network egress
- `ELMOS_HERMETIC_BUILD_ENVIRONMENT_ATTESTATION_CONTROLLER-04` — toolchain mismatch
- `ELMOS_HERMETIC_BUILD_ENVIRONMENT_ATTESTATION_CONTROLLER-05` — replayed attestation
- `ELMOS_HERMETIC_BUILD_ENVIRONMENT_ATTESTATION_CONTROLLER-06` — customer runner reference value

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
