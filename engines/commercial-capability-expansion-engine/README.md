# Elmos Commercial Capability Expansion Engine

This package provides the bounded local, fail-closed runtime for the 85 exact
Commercial Capability Expansion Skills. It accepts only strict JSON-shaped
inputs, resolves exact repository-owned handlers, requires host-verified
invocation authority, persists tenant/project-scoped receipts and exposes a
conservative E0-E5 evidence gate.

Local execution is self-attested engineering evidence only. External providers,
native runtimes, independent verification and production certification remain
`NOT_RUN` / `NOT_CERTIFIED` until separately authorized and evidenced.

The repository importer treats the source ZIP as untrusted data and never runs
its scripts, workflows, policies, or installers. The local SQLite runtime is not
a production deployment profile: an authenticated external journal anchor,
durable tenant storage quotas, retention/garbage collection, deployment
reconciliation, and representative external qualification remain required.
