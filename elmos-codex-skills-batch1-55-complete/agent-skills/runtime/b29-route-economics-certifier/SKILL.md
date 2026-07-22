---
name: b29-route-economics-certifier
description: "Measure and certify route engineering economics: build-green rate, verified workload cost, manual effort, agent cost, runtime burden, maintenance effort, and commercial viability. Use before funding or releasing a route."
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

## Skill 1147: purpose

Prevent technically impressive but economically unsustainable routes from being marketed as mature products.

## Use this skill when

Use when prioritizing routes, completing a certification cycle, pricing a route, or deciding to pause/retire it.

## Workflow

1. Collect reproducible metrics from corpus and real-repository runs.
2. Separate runner, model, storage, review, expert, support, and compatibility-runtime costs.
3. Compute cost per verified migrated module/workload rather than cost per generated line.
4. Measure first-build pass, build-green, P0 behavior pass, repair rounds, manual hours, and maintenance burden.
5. Create base, upside, and downside commercial scenarios.
6. Recommend `commercial`, `limited`, `research`, `pause`, or `retire` with explicit thresholds.

## Required repository outputs

- `routes/<route>/certification/economics.json`
- `routes/<route>/certification/economics-report.md`

## Verification

- All metrics link to run IDs/evidence.
- Manual work is not omitted.
- Model and compatibility-runtime costs are included.
- Sensitivity analysis is present.

## Stop and escalate when

- Metrics rely only on toy corpus.
- Manual expert work is untracked.
- The route loses money under base assumptions without an approved strategic rationale.
- The route cannot be supported with available owners.

## Definition of done

The requested implementation exists in code, manifests validate, required tests pass, evidence is written to the route certification directory, and all remaining unsupported or unknown behavior is explicitly recorded with an owner or blocking status.
