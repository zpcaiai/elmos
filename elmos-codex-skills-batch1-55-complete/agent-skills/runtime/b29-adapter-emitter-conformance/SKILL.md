---
name: b29-adapter-emitter-conformance
description: "Implement or validate source adapter and target emitter conformance to the versioned PSP/UIR contracts, determinism rules, source maps, and engine protocol. Use for engine boundary work across Batch 29 routes."
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

## Skill 1144: purpose

Make language engines interchangeable at the contract boundary without coupling them to platform databases or route-specific framework logic.

## Use this skill when

Use when creating a language adapter, target emitter, engine protocol implementation, or fixing cross-engine contract failures.

## Workflow

1. Locate the canonical engine request/response, PSP, UIR, diagnostic, and source-map contracts.
2. Implement adapter output with stable symbol IDs, source ranges, unsupported nodes, and engine version metadata.
3. Implement emitter input validation and deterministic target output; separate formatting from semantic lowering.
4. Add contract fixtures for valid, invalid, forward-compatible, and unknown-extension cases.
5. Run the engine twice on identical input and compare canonical outputs for determinism.
6. Ensure the engine reads/writes artifacts through protocol boundaries and never writes control-plane tables directly.

## Required repository outputs

- `contracts/psp/`
- `contracts/uir/`
- `contracts/engine-protocol/`
- `engines/<language>-engine/`
- `tests/contracts/engine-conformance/`

## Verification

- Contract schema tests pass.
- Determinism test produces identical canonical digest.
- Source-map coverage meets route threshold.
- Invalid contract inputs fail explicitly rather than being partially accepted.

## Stop and escalate when

- Stable symbol identity cannot be produced.
- The emitter requires framework-specific behavior inside core UIR.
- Unknown nodes are being dropped.
- The implementation needs direct access to another service database.

## Definition of done

The requested implementation exists in code, manifests validate, required tests pass, evidence is written to the route certification directory, and all remaining unsupported or unknown behavior is explicitly recorded with an owner or blocking status.
