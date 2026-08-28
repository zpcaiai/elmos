# Implementation Guide — AI Cost, Pricing and SLA Contract Compiler

## Purpose

Compile machine wall-clock, token, compute, storage, network, provider and support economics into enforceable quotes, budgets, SLAs and settlement evidence.

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

1. Machine-time versus human-review separation
2. Provider/token/compute/storage/network accounting
3. Quote uncertainty and contingency
4. Runtime budget enforcement
5. SLA breach and customer settlement evidence

## Native acceptance corpus

- `ELMOS_AI_COST_PRICING_SLA_CONTRACT_COMPILER-01` — quote calculation
- `ELMOS_AI_COST_PRICING_SLA_CONTRACT_COMPILER-02` — budget enforcement
- `ELMOS_AI_COST_PRICING_SLA_CONTRACT_COMPILER-03` — provider reconciliation
- `ELMOS_AI_COST_PRICING_SLA_CONTRACT_COMPILER-04` — machine ETA reporting
- `ELMOS_AI_COST_PRICING_SLA_CONTRACT_COMPILER-05` — SLA breach
- `ELMOS_AI_COST_PRICING_SLA_CONTRACT_COMPILER-06` — refund/credit rule

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
