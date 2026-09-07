# VeriEQL Adapter

This adapter is an **integration contract**, not a bundled copy of VeriEQL. Production enablement requires:

1. organization-approved license review;
2. exact version and signed container digest;
3. SBOM, vulnerability and provenance checks;
4. all conformance fixtures passing;
5. parser/status mapping review;
6. sandbox and resource-limit verification.

Evidence trust: `BOUNDED`. Declared properties: SQL_BOUNDED_EQUIVALENCE, COUNTEREXAMPLE_DATABASE, COMPLEX_SQL.

The adapter must never translate timeout, unsupported features, crashes, incomplete output, or a bounded search into an unbounded proof.
