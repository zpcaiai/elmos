---
name: dependency-conflict-analyzer
description: Find Maven or Gradle dependency version conflicts and unresolved graph evidence. Use for convergence analysis, duplicate coordinates, BOM drift, split packages, or dependency graph risks.
---
# Dependency Conflict Analyzer

## Workflow
1. Compare declared versions by group and artifact across all modules.
2. Consume approved resolved-tree evidence when available and label its producer/version.
3. Detect convergence conflicts, evictions, duplicate classes and split packages when evidence supports them.
4. Keep static-only and resolved-graph findings distinct.

## Acceptance
- Conflicting declared versions produce deterministic findings.
- Missing transitive resolution cannot pass convergence.
- Findings include coordinates, modules, paths and evidence status.

