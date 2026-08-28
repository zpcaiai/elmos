# Certification Matrix

| Layer | Test | Pass condition |
|---|---|---|
| Domain | Requirement coverage | 100% of must-have requirements have realization paths |
| Domain | Rule consistency | No unresolved critical rule conflict |
| Domain | State machines | Initial and terminal states exist; no illegal dead-end or unbounded loop |
| Domain | Authorization | Default deny; every protected action has an explicit rule |
| Architecture | Style selection | Simplest style satisfying mandatory qualities is selected |
| Architecture | Module graph | No prohibited cycle or unexplained shared write ownership |
| Architecture | Data consistency | One authoritative owner per mutable data set |
| Architecture | Resilience | Critical remote interactions have bounded failure behavior |
| Architecture | Threat model | Every critical threat has mitigation and verification |
| Architecture | Deployment | Restore, rollback, and production topology are defined |
| Blueprint | Version resolution | Runtime, framework, plugin, and dependency versions are pinned |
| Blueprint | Build reproducibility | Clean build contract has no hidden local dependencies |
| Blueprint | Configuration | No production secrets; invalid required configuration fails fast |
| Generation | Template trust | Every template signature and publisher is valid |
| Generation | Source parsing | Every emitted source file parses successfully |
| Generation | Ownership | Every artifact has an unambiguous ownership mode |
| Generation | Idempotency | Same inputs produce no semantic diff |
| Generation | Merge safety | User-owned and protected changes survive regeneration |
| Generation | Quality | Formatter stable; no unresolved error-level lint/type findings |
| Generation | Manifest | All artifacts, dependencies, tools, and provenance are inventoried |
