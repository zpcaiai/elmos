# Integration Design Rules

- One authoritative owner for every mutable data set.
- No cross-service database writes or cross-service foreign keys.
- Domain/persistence entities are not wire contracts.
- Every remote interaction has timeout, error and compatibility semantics.
- Non-idempotent requests are not blindly retried.
- Events are versioned completed facts with owner, key, ordering and retention policy.
- Cache and search stores are derived and rebuildable.
- File access is authorized independently of object-key secrecy.
- Mocks never replace required certification against real compatible infrastructure.
- Breaking contracts require approval, versioning and migration guidance.
