---
name: b29-route-corpus-certifier
description: "Build and evaluate route-specific smoke, semantic, negative, holdout, and real-repository corpora; produce reproducible route benchmark evidence. Use when expanding coverage or making certification claims."
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

## Skill 1145: purpose

Provide independent evidence that a route works beyond hand-crafted happy paths.

## Use this skill when

Use when adding rules, compatibility components, language versions, or preparing a route certification release.

## Workflow

1. Create corpus categories from the route support matrix and known semantic hazards.
2. Add positive, boundary, negative, and unsupported examples with expected outcomes.
3. Separate `development` and `holdout` datasets physically and procedurally.
4. Add at least one representative vertical slice and one real or licensed repository case where available.
5. Run source and target compilers/runtimes and capture build, test, behavior, cost, and duration evidence.
6. Generate `certification/evidence.json` and a human-readable benchmark report.
7. Turn every discovered critical regression into a permanent corpus case.

## Required repository outputs

- `routes/<route>/corpus/development/`
- `routes/<route>/corpus/holdout/`
- `routes/<route>/corpus/real-repository/`
- `routes/<route>/certification/evidence.json`
- `routes/<route>/certification/benchmark-report.md`

## Verification

- All corpus fixtures have manifests and expected outcomes.
- Holdout inputs are not referenced by implementation code or prompts.
- Critical semantic categories have deterministic oracles.
- Benchmark commands and toolchain digests are recorded.

## Stop and escalate when

- Only toy examples pass.
- Holdout data has leaked into rule development.
- A critical category lacks an oracle.
- Real repository licensing or privacy is unclear.

## Definition of done

The requested implementation exists in code, manifests validate, required tests pass, evidence is written to the route certification directory, and all remaining unsupported or unknown behavior is explicitly recorded with an owner or blocking status.
