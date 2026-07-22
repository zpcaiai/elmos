---
name: third-party-package-mapping-engine
description: Plan one-to-one, one-to-many, or many-to-one target package mappings at API and semantic granularity. Use when the target standard library is insufficient.
---
# Third Party Package Mapping Engine
Read `../references/dependency-migration-v1.md`. Map the used API subset, not just package coordinates. Explain component ownership, version constraints, transitive effects, configuration, runtime assets, one-to-many or many-to-one boundaries, adapters and uncovered behavior. Require approved provenance and downstream version/platform/license/security gates. Never add packages merely to preserve the source dependency count, hide an unmapped API, or select from name similarity.
