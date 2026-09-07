---
name: elmos-certified-skill-evolution
description: Convert validated execution lessons into regression-tested, versioned, certifiable production skills.
priority: P1
---

# K7 — Memory → Skill → Corpus → Certification

## Skills

- project-memory
- repository-semantic-memory
- failure-memory
- counterexample-memory
- repair-memory
- lesson-extractor
- lesson-generalizer
- skill-candidate-generator
- skill-similarity-dedup
- skill-conflict-detector
- skill-fixture-generator
- skill-negative-fixture-generator
- mutation-fixture-generator
- regression-corpus-builder
- golden-route-evaluator
- skill-benchmark
- skill-certifier
- skill-promoter
- skill-canary
- skill-versioning
- skill-lineage
- skill-deprecation
- skill-rollback

## Lifecycle

DRAFT
→ EXPERIMENTAL
→ REGRESSION_TESTED
→ GOLDEN_ROUTE_TESTED
→ CERTIFIED
→ PRODUCTION
→ DEPRECATED

## Promotion rule

One successful repair is evidence for a lesson, NOT evidence for a production skill.

Promotion requires:

- generalized trigger;
- bounded scope;
- positive fixtures;
- negative fixtures;
- regression corpus;
- no unacceptable regression on neighboring routes;
- versioned behavior contract;
- certification evidence.

## Acceptance

Skill promotion is deterministic and auditable; production skill rollback is supported by version pinning.
