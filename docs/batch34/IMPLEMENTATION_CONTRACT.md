# Batch 34 implementation contract

## Required typed artifacts

Every portfolio pack owns an exact immutable scope and must contain a Portfolio Inventory, Dependency Graph, Work Unit Plan, Scale Profile, Campaign Plan, DR Replay Plan, support matrix, independent corpora, and certification evidence.

## Execution contract

Distributed activities are idempotent or compensatable, bounded, checkpointed, tenant isolated, versioned, and replayable. External effects use commit tokens. Repositories, work units, graph nodes, tasks, artifacts, and datasets use stable IDs and immutable baselines.

## Evidence contract

A scale claim requires exact environment and dataset manifests, cold and warm runs, failure injection, cost capture, cleanup, holdout, representative portfolios, and source evidence. Failed and inaccessible scope remains in denominators.
