# Alive2 Adapter

This adapter is an **integration contract**, not a bundled copy of Alive2. Production enablement requires:

1. organization-approved license review;
2. exact version and signed container digest;
3. SBOM, vulnerability and provenance checks;
4. all conformance fixtures passing;
5. parser/status mapping review;
6. sandbox and resource-limit verification.

Evidence trust: `BOUNDED`. Declared properties: LLVM_TRANSLATION_VALIDATION, LLVM_REFINEMENT, UB_CHECKING.

The adapter must never translate timeout, unsupported features, crashes, incomplete output, or a bounded search into an unbounded proof.
