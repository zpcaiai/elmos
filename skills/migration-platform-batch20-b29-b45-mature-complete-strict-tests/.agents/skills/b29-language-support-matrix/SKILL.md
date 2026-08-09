---
name: b29-language-support-matrix
description: Create or update the versioned language-route capability matrix with certified, supported, conditional, experimental, detected-only, and blocked statuses. Use when defining or changing what a route claims to support.
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

## Skill 1143: purpose

Turn broad support claims into machine-readable capability profiles linked to tests and known limits.

## Use this skill when

Use when adding language versions, semantics, framework profiles, or changing route support status.

## Workflow

1. Inventory source and target runtime/compiler versions actually present in CI and runner images.
2. Create or update `support-matrix.json` using the schema and template.
3. List each semantic capability separately: types, generics, null, numbers, time, exceptions, async, concurrency, reflection, serialization, interop, and framework boundaries.
4. Link every `certified` capability to test suites and at least one evidence record.
5. Mark incomplete capabilities conditional, experimental, detected-only, or blocked; include fallback strategy and owner.
6. Update customer-visible documentation from the same matrix rather than maintaining a separate manual claim.

## Required repository outputs

- `routes/<route>/support-matrix.json`
- `routes/<route>/certification/support-matrix.md`

## Verification

- Validate JSON structure with `validate_route.py`.
- Check every certified item has non-empty `evidence_refs`.
- Check every blocked or conditional item has `reason` and `strategy`.

## Stop and escalate when

- A requested support status is not backed by executable evidence.
- The route uses unbounded version ranges such as “all Java” or “latest Python”.
- Critical capabilities are omitted instead of marked blocked.
- Customer documentation would overstate the machine-readable matrix.

## Definition of done

The requested implementation exists in code, manifests validate, required tests pass, evidence is written to the route certification directory, and all remaining unsupported or unknown behavior is explicitly recorded with an owner or blocking status.
