---
name: elmos-repo-intake
version: 1.0.0
description: Establish repository topology, build systems, languages, modules, ownership boundaries and runnable validation commands.
---

# Repository Intake

Establish repository topology, build systems, languages, modules, ownership boundaries and runnable validation commands.

## Trigger conditions
- start of repository run

## Inputs
- `repository root`

## Outputs
- `repo profile`
- `build/test command catalog`
- `module map`

## Procedure
1. Inspect manifests and workspace files.
2. Identify services/apps/packages/libraries.
3. Detect build, test, lint, typecheck and migration commands.
4. Capture current git state and uncommitted changes.
5. Mark generated/vendor/large-data paths.

## Guardrails
- Do not mutate repository.
- Never overwrite user changes.

## Acceptance criteria
- repo profile is sufficient for later task planning
- validation commands are executable or explicitly unavailable

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
