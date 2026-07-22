---
name: b37-comparator-normalizer-sdk
description: "Implement a Comparator and Normalizer SDK for canonical observations tolerances masks domain invariants difference classification and anti-cheating controls."
---

# Skill 1311: b37-comparator-normalizer-sdk

## Use this skill when

- New domains need custom behavioral comparison.
- Customers require controlled normalization for dynamic fields.

## Domain-specific risks and invariants

- Overbroad masks and tolerances can erase real regressions.
- Comparator code may expose sensitive observations.

## Workflow

1. Define canonical observation types, normalizer stages, field-level policies, tolerances, invariants, severity, and provenance.
2. Generate SDK and reference comparators.
3. Require explicit forbidden fields for money tenant authorization status transaction and audit outcomes.
4. Add source/target, negative, adversarial, and holdout fixtures.
5. Publish comparator packages with privacy and evidence controls.

## Required repository outputs

- comparator-normalizer SDK and schema
- normalization policy and invariant fixtures
- difference classification evidence

## Verification

- Verify masks cannot remove protected fields.
- Run mutation tests against tolerances and normalization rules.
- Check deterministic replay on immutable observations.

## Stop and escalate when

- A requested normalization removes a protected business or security field.
- Comparator requires raw sensitive data outside approved boundary.

## Definition of done

- One domain comparator handles dynamic data without hiding critical differences.
- All tolerance changes are versioned and approved.
