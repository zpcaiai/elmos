# ADR-0013: Short-lived secret leases

Status: Accepted

## Decision

Secrets are operation- and workspace-scoped leases. Values live in closeable memory and workspace tmpfs files with mode `0400`; the database stores metadata only. Cleanup removes materialized files, revokes the provider lease, and zeros buffers independently of job/artifact success.

## Consequences

Environment variables, argv, image layers, source volumes, durable artifacts, and logs are forbidden secret channels.
