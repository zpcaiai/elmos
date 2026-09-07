# Implementation Guide — Sustainable AI Energy and Carbon Efficiency Certifier

## Purpose

Measure and certify energy, accelerator utilization, embodied/operational carbon assumptions and efficiency trade-offs without weakening required quality, safety or resilience.

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

1. measure energy per accepted task and per model phase
2. bind region electricity and carbon-factor assumptions
3. compare batching, quantization, cache and hardware alternatives
4. apply quality, safety and SLO floors
5. emit bounded sustainability claims with uncertainty

## Native acceptance corpus

- `ELMOS_SUSTAINABLE_AI_ENERGY_CARBON_EFFICIENCY_CERTIFIER-01` — native scenario: measure energy per accepted task and per model phase
- `ELMOS_SUSTAINABLE_AI_ENERGY_CARBON_EFFICIENCY_CERTIFIER-02` — native scenario: bind region electricity and carbon-factor assumptions
- `ELMOS_SUSTAINABLE_AI_ENERGY_CARBON_EFFICIENCY_CERTIFIER-03` — native scenario: compare batching, quantization, cache and hardware alternatives
- `ELMOS_SUSTAINABLE_AI_ENERGY_CARBON_EFFICIENCY_CERTIFIER-04` — native scenario: apply quality, safety and SLO floors
- `ELMOS_SUSTAINABLE_AI_ENERGY_CARBON_EFFICIENCY_CERTIFIER-05` — native scenario: emit bounded sustainability claims with uncertainty

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
