---
name: cobol-modularization-refactor-and-language-transformer
description: Modularize COBOL and create traceable, review-only refactor or target-language candidates while preserving contracts, side effects, data layouts, and business behavior. Use for paragraph or section extraction, adapter isolation, state removal, COBOL-to-Java, or provider-assisted transformation.
---

# COBOL Refactor and Transform

## Refactor before transforming

1. Identify a capability and stabilize its inputs, outputs, copybooks, side effects, data access, error model, and tests.
2. Extract paragraphs or sections, isolate CICS/IMS/data adapters, normalize errors, reduce state, and resolve dynamic calls incrementally.
3. Bind every target fragment to source program, section, paragraph, rule, copybook, provider, provider version, and reviewer.
4. Treat rules-based, AI-assisted, vendor, and manual providers as replaceable candidate generators.
5. Compile and run static, contract, rule, layout, side-effect, performance, and human review gates independently.

## Reject unsafe automation

- Do not auto-approve financial core rules, unresolved calls, assembler boundaries, unknown copybooks, IMS position semantics, autonomous transactions, production side effects, or low-readiness modules.
- Judge semantic and side-effect equivalence, not class shape or method names.
