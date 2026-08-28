# Implementation Depth Standard

Every component Skill has seven files and must contain:

1. domain entities and invariants;
2. typed interfaces and events;
3. persistence, RLS, idempotency and retention;
4. actual algorithms and bounded fallbacks;
5. a durable state machine;
6. native positive, negative, recovery and upgrade tests;
7. a Skill-specific threat model, benchmark and evidence contract.

Common governance language is allowed, but it cannot substitute for target-specific acceptance. A mock-only test cannot satisfy native conformance.
