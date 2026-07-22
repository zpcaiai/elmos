---
name: business-journey-and-system-consistency-validator
description: Validate end-to-end cross-language business journeys and system consistency independently of individual service checks. Use as the Batch 13 system quality gate.
---

# Business Journey and System Consistency Validator

## Workflow

1. Define each journey step, system node, language, input/output contract, expected side effects, timeout, criticality, and model involvement.
2. Execute with approved synthetic or protected data and preserve continuous trace/correlation evidence.
3. Check service results, cross-contract compatibility, final business state, expected messages, duplicate/missing/order behavior, model contracts, system SLOs, compensation, and cleanup.
4. Treat final business invariants as authoritative over individual service green checks.
5. Classify `CONSISTENT`, `EVENTUALLY_CONSISTENT`, `CONSISTENT_AFTER_REPAIR`, `BUSINESS_INVARIANT_FAILED`, `MESSAGE_INCOMPLETE`, `DATA_INCOMPLETE`, or `INCONCLUSIVE`.
6. Keep this quality decision independent from language transformation, repair agents, and traffic providers.

## Gate

Do not pass the system gate on missing journey evidence, broken trace continuity, duplicate or missing messages, failed compensation, incomplete cleanup, or a failed business invariant.
