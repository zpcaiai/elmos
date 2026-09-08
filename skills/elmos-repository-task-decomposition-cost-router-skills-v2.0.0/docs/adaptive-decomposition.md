# Adaptive Hierarchical Repository Decomposition v2

## Why v1 was not enough

A static `requirement -> atomic tasks -> DAG` pipeline is useful but assumes the planner knows the correct task granularity and dependencies before execution. Real repositories violate that assumption: implicit requirements are hidden in tests and sibling code, runtime dependencies are discovered late, and the best task size varies by semantic cohesion and verifier locality.

v2 treats a plan as a versioned hypothesis. It starts coarse, refines only near-term branches, validates dependency edges, and edits the graph when execution evidence disproves an assumption.

## Five planning levels

1. **Goal** — original repository-level outcome.
2. **Capability** — user/system capability that can be reasoned about independently.
3. **ChangeSet** — coherent repository change cluster around a semantic seam.
4. **AtomicTask** — independently executable and verifiable worker unit.
5. **Microstep** — local worker procedure, normally not globally scheduled.

The planner should not fully expand all levels at run start. Only nodes on the refinement frontier are refined.

## Decomposition objective

Do not minimize task size. Minimize expected completed repository cost subject to semantic safety:

`decomposition utility = execution savings + parallelism + context reduction - handoff cost - integration risk - replan risk`

A larger cohesive task can be better than two tiny tasks if splitting creates an unstable contract or forces repeated context reconstruction.

## Granularity score

The reference score uses:

- context demand
- write surface
- semantic breadth
- cross-boundary coupling
- invariant density
- verification distance
- uncertainty

Nodes above the split threshold are refined at the lowest-coupling semantic seam. Nodes below the merge threshold are candidates for merge when separate execution provides little value. Hard invariants can override both thresholds.

## Three graphs, not one

### Behavioral Scenario Graph
Captures observable end-to-end behavior: happy, failure, boundary, compatibility, rollback and operational paths.

### Repository Intelligence Graph (RIG)
Captures typed evidence-backed repository structure: modules, symbols, APIs, data entities, queues, config, build targets and tests; edges represent calls, reads/writes, builds, tests, schema migration and other relationships.

### Execution DAG
Contains only currently executable leaves and typed dependency edges. Every nontrivial edge declares a handoff contract and validator.

This separation prevents file-level dependency structure from replacing product behavior.

## Implicit requirement recovery

Before planning implementation, inspect existing tests, public interfaces, schemas/migrations, sibling implementations, examples, build rules and CI. Inferred requirements must include evidence and confidence. Unresolved high-impact ambiguity becomes an exploration task rather than a hidden assumption.

## Exploration tasks

An exploration task is cheap, bounded and decision-oriented. Examples:

- run one focused failing test to locate behavior;
- inspect runtime trace to determine which implementation is active;
- compile an interface probe;
- create a disposable experiment in a worktree;
- inspect generated schema/client output.

The task must name which planning uncertainty it resolves.

## Validated handoffs

A dependency edge is not considered satisfied merely because the upstream task says `passed`. The producer must emit the declared artifact and the edge validator must confirm that the consumer contract is satisfied. This blocks bad intermediate outputs from contaminating downstream tasks.

## Dynamic replanning

Typical triggers:

- repeated same failure;
- new dependency edge discovered;
- actual write surface exceeds prediction;
- contract/schema changes;
- unexpected regression outside impact map;
- security or invariant violation;
- context pack proven insufficient;
- semantic integration conflict.

Prefer local graph edits. Global replans are reserved for changed requirements or invalid architecture assumptions. Passed evidence is preserved if its assumptions remain valid.

## Integration-first safety

Insert integration checkpoints around:

- public contracts;
- migrations;
- shared schemas/types;
- auth/security boundaries;
- distributed side effects;
- fan-out points with many dependent tasks.

This catches errors before large downstream waves consume a faulty contract.

## Decomposition learning

Record:

- first-pass task success;
- replan rate;
- split/merge after execution begins;
- hidden dependency discovery;
- integration conflict rate;
- context overflow/missing context;
- cost per accepted task;
- cost per certified repository change.

Calibrate granularity and seam quality by repository/task family. Decay old priors after architecture or tooling changes.
