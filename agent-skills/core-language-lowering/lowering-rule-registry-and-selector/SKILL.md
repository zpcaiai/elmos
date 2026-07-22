---
name: lowering-rule-registry-and-selector
description: Register, rank, and deterministically select versioned UIR-to-target lowering rules. Use for rule authoring, conflicts, overrides, provenance, or regeneration impact analysis.
---
# Lowering Rule Registry and Selector
Read `../references/lowering-v1.md`. Require stable ID/version, source dialect/opcode/constraints, target/version, strategy, priority, fidelity, idempotency, dependencies, obligations and tests for every rule.

Rank project through generic rules, then compare satisfied preconditions, fidelity and priority. Block unresolved ties. Allow only one final primary rule per operation. Production rules require tests and idempotency; agent output becomes a rule only after review. Record selection and use rule-version changes to invalidate only affected cached callables.
