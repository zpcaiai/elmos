# ADR-0023: Faithful-first core-language lowering

- Status: Accepted
- Date: 2026-07-21

## Context

Batch 3 provides a multi-view UIR and explicit semantic obligations; Batch 4 provides target declarations, generated regions and a buildable target skeleton. Generating compact target-language code directly from source syntax would make cross-language differences in evaluation order, numeric precision, absence, collections, exceptions, async behavior and cleanup difficult to audit.

## Decision

Batch 5 uses two separately evidenced phases. Phase A lowers each eligible callable to an explicit faithful target implementation and requires target parser, symbol and type validation plus UIR semantic checks. Phase B may apply reversible Level 1/2 target idioms only after Phase A passes and must repeat validation.

Every automatic operation is selected from a versioned, tested and idempotent rule registry using a target-version capability matrix. Equal-ranked rule conflicts block. Compiler and AST/CST/LST emitters are injected language backends; the orchestration core does not fall back to raw string generation or claim success when a backend is missing.

Patches are callable-scoped, atomic and reversible. They locate stable Target Declaration IDs inside protected generated-body regions, verify base hashes and never overwrite manual content. Opaque/dynamic/unsupported operations create bounded agent or manual packets with locked signatures, evaluation order and effect contracts. Agent output remains untrusted until it passes the same validation and any required human gate.

Module gates L-A through L-D measure generation, deterministic/agent/manual/opaque populations, static validation, source mapping and semantic fidelity independently. Static readiness is not behavioral equivalence.

## Consequences

- Faithful output can be verbose, but its transformations and failure boundaries are reviewable.
- Native Java, Python, C# and TypeScript/JavaScript compiler/emitter workers are deployment prerequisites for real code generation; their absence blocks affected callables.
- The current reference module provides deterministic planning, rule/capability governance, safe patching, artifacts and gates. It deliberately does not pretend that generic text templates implement production compiler backends.
- Batch 6 may operate only on individually eligible modules and must preserve open obligations and provenance.
