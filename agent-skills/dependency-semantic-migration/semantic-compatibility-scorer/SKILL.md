---
name: semantic-compatibility-scorer
description: Score candidates against the actually used API surface and semantic profile while enforcing non-compensating blockers. Use for auditable candidate ranking.
---
# Semantic Compatibility Scorer
Read `../references/dependency-migration-v1.md`. Score API coverage, semantic fidelity, target/platform fit, operational fit, maintainability and evidence confidence; emit component scores, gaps, fidelity level and rationale. Required API or semantic gaps, prohibited dependencies, unsupported platforms, unknown license/security/provenance, or unpinned versions are blockers that a total score cannot offset. Rank only selectable candidates and retain all raw evidence. Never present a heuristic score as proof of equivalence.
