---
name: b29-compatibility-runtime-governor
description: Design, implement, budget, and certify compatibility-runtime components used by language routes. Use when target-native code cannot preserve source semantics directly.
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

## Skill 1146: purpose

Keep compatibility layers small, explicit, secure, versioned, and removable instead of becoming a hidden source-runtime emulator.

## Use this skill when

Use when adding wrappers for decimal, optional, collection, exception, reflection, monitor, or other non-directly representable semantics.

## Workflow

1. Document the exact source semantic gap and why direct/idiomatic lowering is insufficient.
2. Search existing runtime components before adding a new one; prefer shared primitives with route-specific adapters.
3. Define a stable API, ownership model, supported versions, and removal/migration path.
4. Add conformance, property, negative, performance, and security tests.
5. Update the route runtime manifest and compatibility budget.
6. Reject runtime use in prohibited domains unless an explicit architecture decision and enhanced verification exist.

## Required repository outputs

- `runtimes/compat/<component>/`
- `routes/<route>/compat-runtime/manifest.json`
- `routes/<route>/certification/compatibility-budget.json`

## Verification

- Runtime tests pass independently of generated applications.
- Route tests prove source-equivalent semantics.
- License/SBOM/security scans pass.
- Budget remains below configured thresholds.

## Stop and escalate when

- The component would hide unknown semantics.
- The runtime is proposed for authentication, authorization, transaction core, or money calculation without explicit approval.
- No exit strategy exists.
- The target team cannot maintain the runtime API.

## Definition of done

The requested implementation exists in code, manifests validate, required tests pass, evidence is written to the route certification directory, and all remaining unsupported or unknown behavior is explicitly recorded with an owner or blocking status.
