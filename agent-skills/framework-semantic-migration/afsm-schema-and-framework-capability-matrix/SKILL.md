---
name: afsm-schema-and-framework-capability-matrix
description: "Model AFSM v1 entities and target framework capability states for REST, DI, persistence, security, configuration, messaging, cache, scheduling, and lifecycle. Use before selecting any Batch 7 recipe."
---
# AFSM Schema and Framework Capability Matrix
Read `../references/afsm-v1.md` and validate against `contracts/framework-schema/afsm-entity.schema.json`. Bind every capability to framework family, programming model and version; classify it as native, configured, third-party, adapter, desugar, external, manual or unsupported.

Record semantic gaps and a fallback for every non-native capability. Keep third-party features distinct from framework-native features. Block preview-only, version-unknown or strategy-free capabilities.

