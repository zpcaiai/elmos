---
name: elmos-requirement-normalizer
version: 1.0.0
description: Convert ambiguous product/engineering requests into explicit scope, non-goals, constraints, acceptance scenarios and unknowns without prematurely coding.
---

# Requirement Normalizer

Convert ambiguous product/engineering requests into explicit scope, non-goals, constraints, acceptance scenarios and unknowns without prematurely coding.

## Trigger conditions
- new feature request
- multi-paragraph requirement
- ambiguous repository task

## Inputs
- `raw requirement`
- `repo metadata`

## Outputs
- `normalized requirement spec`
- `acceptance scenarios`
- `assumption log`

## Procedure
1. Extract business objective and user-visible outcomes.
2. Separate functional/non-functional requirements.
3. List explicit non-goals and invariants.
4. Turn each must-have into observable acceptance scenarios.
5. Record assumptions that can be validated from the repository.

## Guardrails
- Do not invent external requirements.
- Resolve repository-discoverable questions by inspection rather than asking.

## Acceptance criteria
- each must-have maps to >=1 acceptance scenario
- unknowns are classified

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
