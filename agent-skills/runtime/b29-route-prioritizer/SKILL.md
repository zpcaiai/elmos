---
name: b29-route-prioritizer
description: "Score and rank candidate language migration directions using customer demand, revenue potential, technical feasibility, corpus availability, maintenance cost, and strategic fit. Use before approving a new Batch 29 route."
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

## Skill 1142: purpose

Select which directed language route should receive engineering investment and produce an auditable recommendation.

## Use this skill when

Use when choosing among multiple route candidates or reviewing whether an existing route should continue, pause, or retire.

## Workflow

1. Collect candidate routes and evidence; do not infer demand from language popularity alone.
2. Create `docs/batch29/route-candidates.json` from the supplied template.
3. Score candidates with `score_routes.py`; review weights and raw evidence separately.
4. Add sensitivity cases for optimistic, base, and downside assumptions.
5. Recommend one of `approve`, `discovery`, `defer`, or `reject` for each route.
6. Record the decision owner, review date, and the first customer or corpus milestone required.

## Required repository outputs

- `docs/batch29/route-candidates.json`
- `docs/batch29/route-priority-report.md`
- `docs/batch29/route-priority-scores.json`

## Verification

- Run `python3 scripts/batch29/score_routes.py docs/batch29/route-candidates.json --output docs/batch29/route-priority-scores.json`.
- Check every scored field has an evidence note.
- Verify no two opposite directions share a single feasibility score.

## Stop and escalate when

- There is no concrete customer/use-case evidence.
- A route is being approved only because the reverse route exists.
- The engineering capacity or route owner is missing.
- Sensitivity analysis changes the decision materially and management has not resolved it.

## Definition of done

The requested implementation exists in code, manifests validate, required tests pass, evidence is written to the route certification directory, and all remaining unsupported or unknown behavior is explicitly recorded with an owner or blocking status.
