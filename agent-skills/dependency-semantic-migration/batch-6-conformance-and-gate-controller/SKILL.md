---
name: batch-6-conformance-and-gate-controller
description: Aggregate per-module Batch 6 evidence, metrics, blockers, and D-A through D-D gates. Use to decide eligibility for framework migration in Batch 7.
---
# Batch 6 Conformance And Gate Controller
Read `../references/dependency-migration-v1.md`. Compute inventory/resolution, usage/profile, strategy, supply-chain/build and contract/differential coverage per target module. Evaluate D-A through D-D independently, preserving `NOT_RUN`, `BLOCKED`, `INCONCLUSIVE`, rejected candidates, restrictions and open obligations. Require every dependency to be removed with proof or assigned one explicit validated strategy. Only modules passing D-D are eligible for Batch 7; do not average blockers away, inherit another module's pass, or describe D-D as whole-repository behavioral equivalence.
