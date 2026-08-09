---
name: b29-route-certification-gate
description: Run the Batch 29 certification gate for a directed language route and emit pass, limited, experimental, or blocked status from machine-readable evidence. Use only after route implementation and independent holdout evaluation.
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

## Skill 1160: purpose

Make route release claims reproducible, conservative, and tied to actual source/target builds, semantic coverage, behavior evidence, security, economics, and maintainability.

## Use this skill when

Use when a route is proposed for certification, recertification, status downgrade, or release.

## Workflow

1. Validate route manifest, support matrix, compatibility-runtime manifest, corpus layout, and evidence files.
2. Verify source and target toolchain versions and artifact digests are locked.
3. Check certified semantics, build-green evidence, P0 behavior results, holdout independence, source-map coverage, test integrity, and unknown critical counts.
4. Check compatibility budget, license/security results, and route economics.
5. Downgrade rather than pass when evidence supports only limited or experimental status.
6. Write `certification.json`, signed/evidence-ready summary, customer limitations, and next review date.

## Required repository outputs

- `routes/<route>/certification/certification.json`
- `routes/<route>/certification/customer-support-profile.md`
- `routes/<route>/certification/gate-report.md`

## Verification

- Run `python3 scripts/batch29/run_route_gate.py routes/<route>`.
- Validate all evidence references exist and are immutable/digested.
- Run at least one holdout and one representative repository case.
- Check critical semantic drops, behavior regressions, and test-integrity violations are zero.

## Stop and escalate when

- Holdout independence cannot be demonstrated.
- Critical unknown semantics or behavior differences remain.
- The target build is not produced by a real target compiler/runtime.
- Economics or maintenance ownership is missing.
- Support claims exceed measured evidence.

## Definition of done

The requested implementation exists in code, manifests validate, required tests pass, evidence is written to the route certification directory, and all remaining unsupported or unknown behavior is explicitly recorded with an owner or blocking status.
