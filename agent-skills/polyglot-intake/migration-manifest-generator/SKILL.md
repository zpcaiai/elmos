---
name: migration-manifest-generator
description: Freeze all Batch 1 outputs into the versioned migration-manifest.yaml control plane and decide whether Batch 2 may start.
---

# Migration Manifest Generator

## Workflow

1. Require matching `snapshotId` across snapshot, fingerprint, Build Model, inventory, graph, sandbox policy and baseline.
2. Resolve field conflicts from evidence; never silently prefer an inferred value.
3. Assign stable migration/project identifiers and record source/target profiles.
4. Preserve generated/vendor/binary exclusions, risks and every unresolved item.
5. Calculate readiness: build reproducibility 20, tests 20, dependencies 15, type information 15, module decoupling 10, framework support 10, dynamic-feature risk 10.
6. Write all eight manifests plus snapshot ref, log directories and evidence directories atomically.
7. Freeze the manifest version; later changes create a new version linked to the same or a new snapshot.
8. Open Batch 2 only when the mandatory artifacts exist and baseline execution is recorded.

## Gate

`PASSED` requires a complete immutable snapshot, detected projects/build systems, dependency graph, enforced sandbox policy and a non-simulated recorded baseline. Existing failed source tests may be carried forward if named and evidenced. Missing execution or projects yields `BLOCKED`.

## Hard boundaries

- Never erase unresolved values to improve the readiness score.
- Never mix artifacts from different snapshots.
- Batch 1 emits no target-language source code.

## Acceptance

The frozen workspace contains `repository-snapshot.json`, `project-fingerprint.json`, `build-model.json`, `source-inventory.json`, `dependency-graph.json`, `baseline-report.json`, `sandbox-policy.yaml`, and `migration-manifest.yaml`.
