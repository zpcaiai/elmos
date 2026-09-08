---
name: elmos-implicit-requirement-miner
version: 2.0.0
description: Recover implicit repository requirements from executable and structural evidence before implementation planning.
---

# Implicit Requirement Miner

Recover requirements that are not stated in the user prompt but are encoded in the repository.

## Trigger conditions
- normalized requirement exists
- repository intake is available

## Inputs
- `requirement spec`
- `repository intelligence graph`
- `tests/build/config/public interfaces`

## Outputs
- `explicit requirement set`
- `inferred requirement set`
- `evidence links`
- `ambiguity ledger`
- `exploration task requests`

## Procedure
1. Trace every requested behavior to existing tests, public APIs, schemas, examples and sibling implementations.
2. Infer compatibility, error, security, persistence, observability and lifecycle expectations only when repository evidence exists.
3. Tag each inference with source evidence, confidence and consequences if wrong.
4. Detect contradictions between prompt, code, tests and documentation.
5. Convert unresolved high-impact ambiguity into an exploration task instead of silently guessing.
6. Feed confirmed/inferred requirements into scenario graph generation.

## Guardrails
- Never invent hidden requirements without repository evidence.
- Treat tests as behavioral evidence, not automatically as the complete product specification.
- High-risk ambiguity blocks irreversible implementation until explored or explicitly waived.

## Acceptance criteria
- every inferred requirement has evidence and confidence
- contradictions are explicit
- no critical ambiguity is silently embedded in downstream tasks

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
