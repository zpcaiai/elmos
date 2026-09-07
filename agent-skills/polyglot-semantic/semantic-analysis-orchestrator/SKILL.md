---
name: semantic-analysis-orchestrator
description: Orchestrate an evidence-bound Batch 2 semantic run from a passed Batch 1 migration manifest. Use whenever a Java, Python, C#, JavaScript, or TypeScript snapshot must be analyzed, incrementally reanalyzed, or prepared for Batch 3 UIR.
---

# Semantic Analysis Orchestrator

Read `../references/psp-v1.md` before acting.

## Inputs

Require the Batch 1 bundle, repository root, analysis profile, resource budget, and pinned adapter configuration. Reject a snapshot/manifest mismatch or a Batch 1 gate other than `PASSED`.

## Workflow

Verify every source hash; route each file to exactly one most-specific project and primary adapter; process dependency modules before dependents; build syntax before symbols/types/references/calls/CFG; preserve partial results and convert adapter failures into blocking diagnostics. Derive the run and cache IDs deterministically from snapshot, build model, profile, budget, provider versions, and configuration.

## Output and acceptance

Return a PSP `SemanticDataset` and `semantic-run-manifest.json` containing run/snapshot identity, adapter descriptors, projects, artifacts, coverage, diagnostics, configuration hash, and status. Repeated identical inputs must yield stable entity IDs. Never execute repository code, processors, generators, imports, or unknown analyzers. Missing authority may yield syntax evidence, but must block Batch 3.
