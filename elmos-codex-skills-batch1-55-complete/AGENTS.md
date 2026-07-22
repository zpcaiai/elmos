# Combined ELMOS Skill pack rules

- Treat `migration-pack` M1–M45 and `product-commercialization` B34–B55 as separate namespaces.
- Inspect `manifest.json` and the exact `editionStatus` before invoking a Skill.
- `normalized-source-incomplete` and `generated-planning-edition` are not authoritative production contracts.
- Preserve immutable source facts, versions, evidence and decision lineage.
- Never weaken tenant, authorization, privacy, secret, safety, financial or evidence boundaries.
- Static validation does not change external evidence from `NOT_RUN` and cannot certify a Batch.
