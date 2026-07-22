# Language and Integration Certification Matrix

| Area | Required certification |
|---|---|
| Source | Target parser succeeds; no unresolved type/analyzer error |
| Build | Clean isolated build/install/restore with pinned tooling |
| Domain | No framework dependency; invariants and rules verified |
| API | Contract and implementation match; errors/auth explicit |
| Persistence | Migration plus target-compatible database integration tests |
| Security | Unauthenticated, unauthorized and cross-tenant tests fail safely |
| Messaging | Duplicate, retry, timeout, dead-letter and replay tests |
| Container | Non-root, no secrets, health/readiness/shutdown verified |
| Regeneration | Idempotent and preserves protected/user-owned changes |
| Manifest | Every artifact, dependency, contract and tool inventoried |

## Runtime certification sequence

```text
generate → parse → format/analyze/type-check → clean build/install → unit test
→ migrate target database → integration test → start → health check
→ authenticated journey → unauthorized/cross-tenant negative journey → shutdown
```
