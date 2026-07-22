---
name: b29-certify-python-to-typescript
description: Implement or certify the directed Python-to-TypeScript migration route, including source semantics, target lowering, compatibility strategy, corpus, real builds, behavior evidence, and route manifest. Use only for Python source and TypeScript target work.
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

## Skill 1158: Python → TypeScript

Create a customer-usable, independently certified Python → TypeScript route. The reverse direction is not covered by this skill.

## Use this skill when

Use when adding, repairing, benchmarking, or certifying the `python-to-typescript` route.

## Route-specific semantic hazards

- Python truthiness and arbitrary-precision integers versus JavaScript coercion/number
- None versus null/undefined and missing properties
- dict/set ordering, hashing, and equality differences
- sync/async generators and event-loop behavior
- decorators, descriptors, metaclasses, and dynamic attributes
- module loading, exceptions, context managers, and native extensions

## Workflow

1. Inspect `engines/python-engine`, `engines/typescript-engine`, shared PSP/UIR contracts, and any existing `routes/python-to-typescript` package.
2. Run `python3 scripts/batch29/scaffold_route.py --source python --target typescript` if the route package is absent.
3. Define exact source/target compiler and runtime versions in `route.json`; do not use floating “latest” ranges.
4. Implement one complete vertical slice through source parsing, PSP/UIR, route-specific lowering, target emission, target compilation, tests, and behavior comparison.
5. Add deterministic rules for common cases and explicit obligations for unknown or conditional cases.
6. Implement compatibility components only when required and update the compatibility budget.
7. Build corpus cases for every listed semantic hazard, plus negative and unsupported cases.
8. Run development and holdout corpora with independent target compiler/runtime validation.
9. Generate evidence, economics, and support-matrix updates; request certification through the gate skill.

## Required repository outputs

- `routes/python-to-typescript/route.json`
- `routes/python-to-typescript/support-matrix.json`
- `routes/python-to-typescript/lowering/`
- `routes/python-to-typescript/mappings/`
- `routes/python-to-typescript/compat-runtime/manifest.json`
- `routes/python-to-typescript/corpus/development/`
- `routes/python-to-typescript/corpus/holdout/`
- `routes/python-to-typescript/certification/evidence.json`

## Verification

- Run the real Python source compiler/runtime and the real TypeScript target compiler/runtime.
- Run semantic, boundary, negative, unsupported, and holdout corpus suites.
- Verify every generated public symbol has source trace.
- Run `python3 scripts/batch29/validate_route.py routes/python-to-typescript` and the route gate.
- Verify critical behavior differences and unknown critical semantics are zero for certified scope.

## Stop and escalate when

- A listed Python truthiness and arbitrary-precision integers versus JavaScript coercion/number cannot be preserved, adapted, or explicitly blocked.
- A listed None versus null/undefined and missing properties cannot be preserved, adapted, or explicitly blocked.
- A listed dict/set ordering, hashing, and equality differences cannot be preserved, adapted, or explicitly blocked.
- The route only compiles by introducing broad dynamic/any/object fallbacks.
- The requested capability lacks target-runtime or behavior evidence.
- A route-specific framework assumption is being embedded into core UIR instead of a framework pack.

## Definition of done

The directed route has a versioned manifest, explicit support matrix, compiling target vertical slice, development and holdout evidence, source maps, compatibility budget, economics record, and no silent semantic drops in certified scope.
