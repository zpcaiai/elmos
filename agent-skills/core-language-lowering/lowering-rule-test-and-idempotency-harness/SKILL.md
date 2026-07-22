---
name: lowering-rule-test-and-idempotency-harness
description: Test lowering rules with golden, parser, compiler, semantic, property, metamorphic, source-map, and idempotency checks. Use before promoting or changing any production rule.
---
# Lowering Rule Test and Idempotency Harness
Read `../references/lowering-v1.md`. Cover rule unit, operation fragment, callable, type, module, repository fixture and selected cross-language round trips for each supported target version. Golden output checks structure/imports/format only; pair it with compiler and semantic evidence.

Use property tests for numeric/optional/collection/equality/range/string/serialization semantics and metamorphic safe-renaming/parentheses cases. Verify generation and idiomatization are individually idempotent. Disable production rules immediately on idempotency or edge-case regression and trace failures to rule version.
