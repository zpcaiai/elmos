---
name: target-dependency-and-build-patch-emitter
description: Emit reversible target build dependency patch plans and validate native lockfile regeneration in a sandbox. Use after approved decisions.
---
# Target Dependency And Build Patch Emitter
Read `../references/dependency-migration-v1.md`. Produce deterministic add/remove/version/repository/plugin/project-reference/runtime-asset operations for Maven/Gradle, NuGet, Python and npm-family builds, with file ownership, base hashes and rationale. Apply through ecosystem-aware AST/model tooling; ask the target package manager to regenerate locks with network and lifecycle scripts denied, then capture exact resolved graph and hashes. Never hand-edit locks, run install scripts, add unapproved registries, overwrite manual changes, or mark D-C passed from a syntactically edited manifest.
