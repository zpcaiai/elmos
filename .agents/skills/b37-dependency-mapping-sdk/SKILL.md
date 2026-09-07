---
name: b37-dependency-mapping-sdk
description: Implement a Dependency Mapping SDK for package coordinates API capability mappings provider substitutions compatibility adapters license constraints and validation evidence.
---

# Skill 1310: b37-dependency-mapping-sdk

## Use this skill when

- A new library ecosystem or provider mapping must be added.
- Dependency substitutions currently live in hard-coded tables.

## Domain-specific risks and invariants

- Name similarity does not imply API behavioral equivalence.
- License security and operational requirements can invalidate a technically plausible substitute.

## Workflow

1. Define source/target package identity, version ranges, API capabilities, behavior constraints, provider requirements, license/security metadata, migration strategy, and validation references.
2. Generate mapping APIs and resolver hooks.
3. Implement conflict, ambiguity, transitive impact, and version-selection rules.
4. Add compile, contract, security, and license fixtures.
5. Publish mappings with immutable provenance and revocation support.

## Required repository outputs

- dependency mapping SDK and schemas
- mapping registry records and resolver fixtures
- license security and behavior evidence

## Verification

- Resolve exact package versions and transitive dependencies.
- Reject ambiguous or unapproved substitutions.
- Run real build and contract tests for supported mappings.

## Stop and escalate when

- License rights are unclear.
- No behavior evidence exists for a critical API.
- Mapping requires an unapproved provider or data egress.

## Definition of done

- Mappings are typed, versioned, evidence-backed, and revocable.
- Critical APIs never fall back to name-only substitution.
