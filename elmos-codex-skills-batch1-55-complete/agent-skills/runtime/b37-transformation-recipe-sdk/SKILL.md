---
name: b37-transformation-recipe-sdk
description: "Implement a typed Transformation Recipe SDK for predicates semantic rewrites obligations fixtures previews conflict behavior risk classification and deterministic publication."
---

# Skill 1309: b37-transformation-recipe-sdk

## Use this skill when

- Customers or partners need to author reusable migration recipes.
- Existing transformations are untyped scripts or repository-specific patches.

## Domain-specific risks and invariants

- Unbounded scripts can alter security tests transactions or customer-owned code.
- A recipe that passes one fixture can still damage unrelated repositories.

## Workflow

1. Define typed match predicates, semantic preconditions, rewrite operations, postconditions, obligations, ownership constraints, risk tier, and rollback metadata.
2. Generate authoring APIs, CLI, fixtures, preview renderer, and deterministic serialization.
3. Implement conflict detection and composition ordering.
4. Require development, negative, holdout, and representative fixtures.
5. Sign and publish only recipes passing test-integrity and policy gates.

## Required repository outputs

- recipe SDK, schema, compiler, and reference recipes
- fixture and holdout harness
- recipe digest, signature, provenance, and compatibility data

## Verification

- Compile recipes without dynamic code execution.
- Run idempotency, composition, negative, and holdout tests.
- Verify protected and customer-owned regions cannot be overwritten.

## Stop and escalate when

- The recipe requires arbitrary code or shell execution.
- Postconditions cannot detect semantic loss.
- Risk tier or owner is missing.

## Definition of done

- A third party can author, test, sign, and publish a deterministic recipe.
- Every change is explainable and reversible.
- Unsafe compositions are rejected.
