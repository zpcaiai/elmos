---
name: b36-recipe-mapping-authoring
description: "Implement visual and code-based authoring for recipes mappings predicates transformations fixtures tests previews certification and publication without allowing untyped or unsafe scripts."
---

# Skill 1300: b36-recipe-mapping-authoring

## Use this skill when

- Migration experts need to create and refine mappings without modifying core engines.
- A visual authoring experience must emit the same typed artifacts as the SDK and code workflow.

## Domain-specific risks and invariants

- Low-code recipe builders can hide arbitrary code, weak predicates, missing negative tests, or unsafe broad transformations.
- Visual and code representations can drift and produce non-reproducible results.

## Workflow

1. Reuse Batch 29-33 recipe, adapter, mapping, target-profile, and evidence contracts.
2. Define a canonical typed authoring model with source pattern, preconditions, target action, obligations, risks, fixtures, tests, compatibility, and publication metadata.
3. Implement visual editors, code view, round-trip serialization, schema validation, preview, diff, and local corpus execution.
4. Require negative, holdout, compatibility, ownership, security, and test-integrity evidence before promotion.
5. Implement versioning, review, signing, publication, deprecation, rollback, and dependency impact.

## Required repository outputs

- `authoring/profile.json`, typed recipe/mapping model, editor schemas and generated artifacts
- Round-trip, preview, corpus, signing, publication, and rollback evidence
- Examples for semantic, framework, database, client, and cloud mappings

## Verification

- Round-trip visual-to-code-to-visual without semantic loss.
- Run positive, negative, holdout, overlap, ambiguity, ownership, and security tests.
- Reject arbitrary scripts, unbounded matchers, missing preconditions, and unresolved conflicts.
- Verify published artifacts pass their owning Batch gate.

## Stop and escalate when

- A transformation cannot be expressed in the typed model without arbitrary code.
- Predicates overlap ambiguously or apply beyond approved scope.
- Negative or holdout evidence is missing.
- Publication would bypass signing, review, or certification.

## Definition of done

- Visual and code authoring produce identical versioned artifacts.
- Recipes are previewable, testable, reviewable, signed, and reversible.
- Unsafe or ambiguous transformations fail closed.
- Published assets retain complete provenance.
