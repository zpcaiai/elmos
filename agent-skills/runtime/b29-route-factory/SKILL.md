---
name: b29-route-factory
description: "Implement and certify a source-to-target programming-language migration route, including adapters, PSP/UIR mappings, target lowering, compatibility runtime, corpus, benchmarks, and certification. Use for Batch 29 route creation or major route expansion; not for framework-only changes or production cutover."
---

## Operating mode

Work in the repository. Inspect existing code and contracts before editing. Implement the smallest production-shaped slice that satisfies this skill; do not stop at a design document when code can be written and tested.

Read these shared contracts first:

- `../../../docs/batch29/IMPLEMENTATION_CONTRACT.md`
- `../../../docs/batch29/QUALITY_GATES.md`
- `../../../docs/batch29/REPOSITORY_LAYOUT.md`

Use the supplied helpers where applicable:

- `python3 scripts/batch29/scaffold_route.py ...`
- `python3 scripts/batch29/validate_route.py ...`
- `python3 scripts/batch29/run_route_gate.py ...`

## Global constraints

- Never claim a route, semantic capability, or framework mapping is supported without executable evidence.
- Keep source and target directions independent; reverse migration is a separate route.
- Do not silently map unresolved types to `object`, `Any`, or `dynamic`.
- Keep holdout cases separate from development corpus cases.
- Prefer deterministic rules and certified compatibility components before model-generated patches.
- Preserve source-to-target traceability for every generated public type and callable.
- Record unsupported and unknown behavior explicitly; never hide it with TODOs or permissive stubs.
- Run the narrowest relevant tests first, then the route gate before declaring completion.

## Skill 1141: purpose

Turn a requested language pair into a versioned, testable, evidence-backed route package that Codex can build incrementally in this repository.

## Use this skill when

Use when a user asks to add a new language direction, complete an incomplete route, or certify a route for customer use.

## Workflow

1. Inspect existing engines, contracts, route packages, tests, and build commands. Write a short gap inventory in `routes/<route>/certification/gap-inventory.md`.
2. Run the route-priority and support-matrix workflows when the route is not already approved.
3. Scaffold the route with `scaffold_route.py` if it does not exist; keep existing code and adapt paths rather than duplicating engines.
4. Implement or extend the source adapter so it emits versioned PSP that passes contract validation.
5. Implement route-specific PSP-to-UIR semantics and target lowering for one complete vertical slice before broadening coverage.
6. Add compatibility-runtime components only for semantics that cannot be expressed safely and record their budget impact.
7. Create smoke, semantic, negative, holdout, and real-repository corpus cases. Keep holdout inputs out of rule development.
8. Run source build, target build, behavioral checks, and route gate. Fix systemic failures at adapter/rule/generator level before local patches.
9. Generate certification and economics evidence. Mark the route certified only through the gate skill.

## Required repository outputs

- `routes/<source>-to-<target>/route.json`
- `routes/<source>-to-<target>/support-matrix.json`
- `routes/<source>-to-<target>/lowering/`
- `routes/<source>-to-<target>/mappings/`
- `routes/<source>-to-<target>/compat-runtime/`
- `routes/<source>-to-<target>/corpus/`
- `routes/<source>-to-<target>/certification/evidence.json`

## Verification

- Run repository-native engine, contract, and target compiler tests.
- Run `python3 scripts/batch29/validate_route.py routes/<route>`.
- Run `python3 scripts/batch29/run_route_gate.py routes/<route>`.
- Verify at least one real or representative vertical slice builds in the target toolchain.

## Stop and escalate when

- The requested direction lacks an approved route priority or owner.
- Critical source semantics cannot be represented, adapted, or blocked explicitly.
- The only path to green is weakening tests, using permissive dynamic types, or hiding unknown behavior.
- Holdout or real-repository evidence is unavailable for a certification claim.

## Definition of done

The requested implementation exists in code, manifests validate, required tests pass, evidence is written to the route certification directory, and all remaining unsupported or unknown behavior is explicitly recorded with an owner or blocking status.
