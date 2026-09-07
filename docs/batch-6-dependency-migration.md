# Batch 6 dependency semantic migration

`modules/dependency-migration` implements the deterministic Batch 6 control plane. It normalizes per-project dependencies, accepts an authoritative resolved graph, joins actual API-use evidence, builds semantic profiles, evaluates reviewed cross-ecosystem mappings, applies target and supply-chain policy, plans adapters/boundaries, emits declarative build patches, and aggregates D-A through D-D.

## External authorities required for a live migration

1. Ecosystem-native manifest and lock parsers plus a sandboxed resolver for Maven/Gradle, NuGet, Python and npm-family projects.
2. Batch 2/3 symbol, call, reflection/dynamic-load and native-load coverage tied to the frozen source snapshot.
3. Versioned mapping knowledge with source/target version ranges, API mappings, semantic claims, provenance and approval.
4. Exact license, vulnerability, integrity, registry, native-asset, platform and support evidence at a recorded observation time.
5. An ecosystem-aware target build backend that applies only the approved patch, denies lifecycle scripts, regenerates the lockfile and records the resolved graph and artifact hashes.
6. Source-versus-target API contract and differential harnesses, including lifecycle, cancellation, resource, serialization and service-boundary failures.

## Evidence boundary

The nine unit tests use injected deterministic fakes to prove orchestration properties: complete-use-only removal, explicit semantic mapping, supply-chain fail-closed behavior, rejection of name similarity and out-of-range knowledge, resolved-graph integrity, D-C blocking without build resolution, target-repository non-mutation and stable IDs. They do not prove any real package equivalent, license state, vulnerability state, build resolution or migrated behavior.

The 24 Batch 6 skills live in `agent-skills/dependency-semantic-migration`; the shared protocol is `references/dependency-migration-v1.md`; seven JSON Schemas live in `contracts/dependency-schema`.
