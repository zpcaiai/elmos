---
name: behavior-canonicalization-protocol
description: "Define auditable, versioned Batch 9 canonicalization rules that remove nonsemantic noise without masking business differences. Use when raw source-target output formats differ."
---

# Behavior Canonicalization Protocol

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Preserve raw values before any transformation.
2. Apply lossless field order, whitespace, line-ending, path, header-case or one-to-one ID mappings.
3. Require contract evidence and approval for conditional order, time, exception or numeric rules.

## Hard rules

- Forbid rules that hide money, authorization, tenant, status, counts, transactions, audit or deletion.
- Scope every rule by observation and field.
- Do not let an Agent create or approve a rule.

## Output

Emit canonical observations linked to rule versions and raw evidence.

