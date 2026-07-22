# ADR-0056: Separate product Batch 27-34 from Migration Pack M29-M34

## Status

Accepted on 2026-07-22.

## Decision

Use `Product Batch 27-34` for the commercial roadmap and `Migration Pack M29-M34` for the independently supplied certification toolkits. Preserve the package directories `docs/batch29` through `docs/batch34` for their existing relative Skill references, but require the `M` prefix in Java models, APIs and new documentation.

Install the package's 124 Skills both in the repository-scoped `.agents/skills` catalog and the ELMOS `agent-skills/runtime` catalog. Install the commercial roadmap's 165 unique Skill contracts only in `agent-skills/runtime`. Record original names, installed aliases, source lines and digests in a manifest.

## Consequences

Overlapping numbers cannot silently overwrite modules, migrations, status or certification claims. Existing package paths remain compatible. A structural package pass remains distinct from a product roadmap decision and from real external certification.
