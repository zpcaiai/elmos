---
name: elmos-requirement-normalizer
version: 2.0.0
description: Normalize explicit requirements and separate repository-discoverable unknowns from product ambiguities before planning.
---

# Requirement Normalizer v2

Convert the raw request into an evidence-oriented specification without prematurely choosing implementation files.

## Inputs
- `raw requirement`
- `repo metadata`

## Outputs
- `explicit requirement spec`
- `non-goals`
- `constraints`
- `observable acceptance criteria`
- `unknown/ambiguity ledger`

## Procedure
1. Extract business objective, user-visible outcome and system-visible side effects.
2. Separate functional, non-functional, compatibility and operational constraints.
3. Identify explicit non-goals and irreversible decisions.
4. Turn each must-have into observable acceptance criteria, not implementation prescriptions.
5. Split unknowns into repository-discoverable, product-decision and external-dependency classes.
6. Route repository-discoverable unknowns to `elmos-implicit-requirement-miner`; never ask the user for facts the repository can answer.
7. Assign consequence-of-error and confidence to each unresolved ambiguity.

## Guardrails
- Do not infer hidden requirements here; that requires repository evidence.
- Do not decompose by files until behavioral scenarios and repository graph exist.

## Acceptance criteria
- every must-have maps to observable evidence
- unknowns are classified and high-impact ambiguity is visible

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
