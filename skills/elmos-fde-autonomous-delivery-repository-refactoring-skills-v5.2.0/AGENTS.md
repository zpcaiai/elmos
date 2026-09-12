# Elmos FDE Skills Package — Agent Map

## Mission

Implement this package as a non-routable capability extension to the existing Elmos v5.1.0+ architecture. Preserve one canonical owner for Goal, AI-SIR, repository facts, semantic truth, runtime authority, effects, evidence and completion.

## Start here

1. Read `README.md` and `docs/00_PACKAGE_SCOPE_AND_BOUNDARIES.md`.
2. Read `catalog/package.yaml`, `catalog/kernel-ownership.yaml`, and `catalog/route-bindings.template.yaml`.
3. Select a batch from `catalog/implementation-batches.yaml`; find exact tasks in `catalog/implementation-tasks.json`.
4. Read only the active atomic Skill's five files under `skills/atomic/`.
5. Maintain the execution plan in `PLANS.md` or the target repository's canonical planning artifact.

## Non-negotiable invariants

- Do not add a routable entry point. Every component Skill remains `routable: false`.
- Do not create a second Goal store, AI-SIR owner, runtime authority, Effect Ledger, Evidence Ledger or K8 completion authority.
- Resolve symbolic bindings against the target registry. Missing or ambiguous P0 bindings fail closed.
- Bind work to exact tenant, engagement, RevisionSet, environment, Skill/Adapter/tool/model/policy versions.
- Default deny. Production writes are prohibited by this capability package.
- Checkpoint before external effects and after accepted ChangeSets. Resume requires lossless authority replay.
- Intercept tool results before commit; fence stale executors and workspaces.
- Preserve Observed, Verified-Absent, Unknown and Unsupported coverage states.
- Producer and verifier must be separate. Maximum local claim: E3.

## Implementation behavior

- Prefer a thin vertical slice over horizontal scaffolding: schema → persistence → service/workflow → Adapter → API/UI → tests → evidence.
- Prefer compiler/LSP/LST/AST or typed transformation recipes over free-form patches.
- Keep atomic commits small, purpose-bounded, independently testable and reversible.
- Use native compilers, test runners, databases and analyzers as authoritative evidence where available.
- For multi-hour work, update `PLANS.md` after each accepted checkpoint with decisions, discoveries, failures and next gates.
- Do not paper over failing checks. Record exact commands, outputs, environment and blockers.

## Required commands

```bash
./validate.sh --strict
python3 -m unittest discover -s tests -v
python3 scripts/validate_package.py . --strict
python3 scripts/validate_json_schemas.py .
python3 scripts/validate_skill_evals.py .
bash scripts/smoke_test_install.sh
python3 scripts/build_release.py . --output-dir ../release
```

## Completion response

State changed files, tests executed, evidence produced, unresolved warnings/unknowns, rollback path, and exact next independent gate. Never infer production readiness from generated files or green package tests.
