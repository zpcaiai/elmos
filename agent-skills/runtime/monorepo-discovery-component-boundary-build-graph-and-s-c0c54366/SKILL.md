---
name: monorepo-discovery-component-boundary-build-graph-and-s-c0c54366
description: "Discover Monorepo technologies, build roots, components, ownership, forward and reverse dependencies, generated sources, shared configuration, and produce evidence-backed workspace slices for analysis, build, migration, and verification."
---

# Objective

Convert a large Repository into an evidence-backed component graph and
materialization plan.

A directory alone is not a component.

# Domain model

Create:

```text
workspace.monorepo_profiles
workspace.monorepo_detection_runs
workspace.monorepo_build_roots
workspace.monorepo_components
workspace.monorepo_component_versions
workspace.monorepo_component_paths
workspace.monorepo_component_dependencies
workspace.monorepo_component_reverse_dependencies
workspace.monorepo_shared_files
workspace.monorepo_generated_source_inputs
workspace.monorepo_ownership_rules
workspace.monorepo_slice_profiles
workspace.monorepo_slice_plans
workspace.monorepo_slice_paths
workspace.monorepo_slice_findings
workspace.monorepo_slice_verifications
