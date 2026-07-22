---
name: uir-schema-and-dialect-registry
description: Define or extend UIR v1 entities, dialects, operations, types, verifier rules, and compatibility. Use whenever Batch 3 schema or dialect behavior changes.
---
# UIR Schema and Dialect Registry
Read `../references/uir-v1.md`. Register globally unique versioned dialects; declare operand/result, region/terminator, effect, verifier, and lowering constraints. Unknown dialects must round-trip as opaque. Minor versions may add optional facts; changed semantics, IDs, flow, nullability, or removals require a major version. Accept only when core loads independently and every entity ID/schema verifies.
