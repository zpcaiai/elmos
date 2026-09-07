# ELMOS Project Synthesis Engine — Batch 46–48

This package contains the implementation-grade Skill specifications for the first three batches of the ELMOS Project Synthesis Engine.

## Included

- Batch 46: Project Synthesis foundation contracts — PG001–PG010
- Batch 47: Natural-language requirement ingestion — PG011–PG020
- Batch 48: Requirement normalization and quality governance — PG021–PG032
- PSIR, synthesis-run, and artifact-graph JSON Schemas
- Predictive-maintenance PSIR example
- Dependency graph
- Acceptance matrix
- Per-batch manifests and global index

## Repository Layout

```text
elmos-project-synthesis-batch-46-48/
├── skills/
│   ├── batch-46/
│   ├── batch-47/
│   └── batch-48/
├── schemas/
├── examples/
├── docs/
├── batch-46-manifest.json
├── batch-47-manifest.json
├── batch-48-manifest.json
└── index.json
```

## Recommended Execution Order

1. Install and certify PG001–PG010.
2. Register the engine contract, state machine, policy model, and evidence model.
3. Install PG011–PG020 and validate a multi-turn requirement discovery session.
4. Install PG021–PG032 and certify requirement baseline readiness.
5. Only then proceed to Batch 49 domain modeling and Batch 50 architecture planning.

## Minimum Gate Before Batch 49

- A natural-language session can produce a versioned PSIR draft.
- Every requirement has source provenance.
- Assumptions and unresolved questions are explicit.
- Conflicts, scope status, priority, risk, and acceptance criteria are available.
- Definition of Ready can approve or block a release slice.
- The approved requirement baseline is immutable and content-addressed.
- Requirement changes produce a bounded impact report.

## Design Rule

No code generator may consume raw conversation text directly. Generators consume only an approved PSIR or a later approved Project Blueprint.
