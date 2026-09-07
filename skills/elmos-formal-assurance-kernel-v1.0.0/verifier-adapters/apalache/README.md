# Apalache Adapter

This adapter is an **integration contract**, not a bundled copy of Apalache. Production enablement requires:

1. organization-approved license review;
2. exact version and signed container digest;
3. SBOM, vulnerability and provenance checks;
4. all conformance fixtures passing;
5. parser/status mapping review;
6. sandbox and resource-limit verification.

Evidence trust: `BOUNDED`. Declared properties: TLA_SYMBOLIC, BOUNDED_MODEL_CHECKING, INDUCTIVE_INVARIANTS.

The adapter must never translate timeout, unsupported features, crashes, incomplete output, or a bounded search into an unbounded proof.
