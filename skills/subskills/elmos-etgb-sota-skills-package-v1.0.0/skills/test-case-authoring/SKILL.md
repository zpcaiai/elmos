---
name: test-case-authoring
description: Create, review, materialize, and maintain executable ETGB test cases and capability matrices.
---

# Test Case Authoring

## Invoke when

Adding a language pair, Spring migration feature, generation requirement, SQL construct, incident regression, public corpus, fault scenario or new Oracle.

## Inputs

- business requirement or defect;
- source and target semantics;
- capability ID and matrix dimensions;
- trusted expected behavior;
- available fixture/corpus and execution environment.

## Authoring workflow

1. **Define the contract before the implementation.** State observable inputs, outputs, state, side effects, errors, ordering, security and performance limits.
2. **Choose the smallest isolating level.** Prefer L0/L1 for root-cause precision; add L2/L3/L4 replay when repository interactions matter.
3. **Create normal and adversarial variants.** Include zero/empty/null, boundaries, Unicode, timezone, concurrent calls, failure before/after side effects and unauthorized actors as applicable.
4. **Select independent Oracle.** The generator or converter under test must not create its own final expected value.
5. **Add a realistic mutant.** Prove the test fails if the target silently drops or changes the intended semantics.
6. **Specify environment and cleanup.** Pin toolchains and dependencies; define no-network/allowlist, resource limits, seed and timeout.
7. **Specify forbidden differences.** Silent loss, data corruption, permission expansion and unreported manual changes are always forbidden.
8. **Materialize and validate.** Run `etgb materialize`, `etgb validate`, `etgb coverage` and the fixture.
9. **Review.** Domain owner reviews semantics; test owner reviews Oracle; security owner reviews dangerous execution.

## Case quality gate

A case is not accepted merely because JSON Schema passes. It must be able to fail for the intended defect, produce a first difference, clean up safely, and remain deterministic or explicitly statistical.

## Incident rule

Every production defect creates:

- a minimal case;
- a realistic repository replay when applicable;
- a hidden variant;
- a mutant reproducing the defect;
- a link to root cause and fixed candidate digest.

## Stable IDs

Do not rename IDs when titles change. If expected semantics changes, version the case and preserve old evidence. Matrix-generated IDs must remain deterministic from their dimension tuple.
