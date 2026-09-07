---
name: python-target-profile-and-migration-planner
description: Select evidence-bound Python targets and staged migration DAGs separately for Web applications, data pipelines, and AI/ML systems. Use for Python version/framework/profile selection, compatibility constraints, GPU/native blockers, or migration sequencing.
---

# Python Target Profile and Migration Planner

## Select from a compatibility snapshot

Load a dated registry covering Python support, framework versions, wheels, private packages, OS/architecture, native extensions, CUDA/driver/cuDNN, deployment, and support windows. Never hardcode a live target as permanently current. Exclude prerelease Python from production by default.

Create distinct profiles for:

- Web: HTTP, auth/session, ORM/migration, and deployment compatibility.
- Data pipeline: schema, dtype, ordering, schedule/retry/backfill, idempotency, and numerical behavior.
- AI/ML: artifact load, features/signatures, inference metrics, training evidence, hardware, and performance.

Treat GPU, native extension, unavailable wheel, Python-2-only dependency, unsupported Django/Flask extension, hidden Notebook state, unknown data semantics, and unloadable model artifacts as hard constraints.

## Build a staged DAG

Order environment restoration, baseline freeze, Python 2/bytes-text work, packaging, interpreter, dependencies, framework/scientific/model changes, native rebuilds, path-specific validation, and deployment. Do not combine Python 2, framework, scientific stack, database, and deployment upgrades into one step.

Attach executor policy, project IDs, dependencies, validations, blockers, Evidence refs, and rollback boundary to every step. Accept only when Web/Data/ML paths differ, no prerelease target slips through, compatibility evidence controls versions, and every blocker has evidence.

