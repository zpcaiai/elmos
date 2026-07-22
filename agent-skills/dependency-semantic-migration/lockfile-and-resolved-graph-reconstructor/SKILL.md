---
name: lockfile-and-resolved-graph-reconstructor
description: Reconstruct exact per-project resolved dependency graphs from authoritative manifests and lockfiles. Use before dependency strategy selection.
---
# Lockfile And Resolved Graph Reconstructor
Read `../references/dependency-migration-v1.md`. Use ecosystem-native lock semantics and an injected, sandboxed resolver when static lock evidence is insufficient. Record nodes, versions, hashes, repositories, scopes, optionality, platform selectors, conflicts, overrides and why each edge exists. Separate declared, resolved/build, runtime-loaded, native and remote-service graphs. Do not treat a manifest range as an exact resolution, flatten transitive ownership, execute lifecycle scripts, or repair a lockfile by hand. Mark the graph incomplete when a private source, conditional edge or resolver result lacks evidence.
