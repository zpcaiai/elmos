---
name: target-build-graph-generator
description: Generate the unified target project/build graph and language-specific build descriptors. Use after target modules and stack are decided.
---
# Target Build Graph Generator
Read `../references/skeleton-v1.md`. Emit project/source/test/resource roots, project references, separated production/test packages, compiler options and commands for Maven/Gradle, pyproject, MSBuild, or npm/TypeScript workspaces. Dependency states remain resolved/provisional/wrapper/retained/unresolved/prohibited. Never invent versions, hardcode secrets, mix project/package edges, leak test dependencies, or produce inconsistent multi-module settings.
