---
name: validation-contract-migrator
description: "Migrate binding, schema, field, object, cross-field, method, custom, async, and domain validation contracts. Use for framework DTO and request validation changes."
---
# Validation Contract Migrator
Read `../references/afsm-v1.md`. Separate transport coercion, validation, domain invariants and database constraints. Preserve required versus nullable, nested cascade, groups, conditional/custom/async rules, collection strategy, paths, codes and localization.

Preserve the error status and shape, and never echo sensitive rejected values. Create contract tests for coercion and error differences. Block empty custom validators, lost groups or synchronous blocking replacements for async validation.

