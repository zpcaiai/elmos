# Build-cache tenant isolation v1.2

This exact Batch 35 P0 verification pack scopes the build-cache v1.2 tenant,
principal, evidence, affinity, environment, context, idempotency, and metadata
ownership boundaries. It references implementation bytes through an exact
artifact manifest and does not copy implementation code.

All execution evidence starts at `NOT_RUN`. The checked-in decision is
`NOT_CERTIFIED`; static structure validation or source inspection cannot raise
that state.

The package ZIP is treated as untrusted source intent. Its scripts were not
executed by this verification pack.
