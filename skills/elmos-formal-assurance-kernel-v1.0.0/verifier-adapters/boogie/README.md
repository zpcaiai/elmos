# Boogie Adapter

This adapter is an **integration contract**, not a bundled copy of Boogie. Production enablement requires:

1. organization-approved license review;
2. exact version and signed container digest;
3. SBOM, vulnerability and provenance checks;
4. all conformance fixtures passing;
5. parser/status mapping review;
6. sandbox and resource-limit verification.

Evidence trust: `SOLVER_TRUSTED`. Declared properties: VERIFICATION_CONDITIONS, HOARE_LOGIC, RELATIONAL_PROGRAMS.

The adapter must never translate timeout, unsupported features, crashes, incomplete output, or a bounded search into an unbounded proof.
