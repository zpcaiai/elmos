# ADR-0051: Independent software-delivery platform engine

## Status

Accepted on 2026-07-22.

## Decision

Implement Batch 22 as an independent Worker backed by the shared evidence-bound transport core. SCM history, pipeline components, artifacts, environments, Golden Paths, self-service and DORA observations keep separate gates. Provider actions require a short-lived lease, exact scope and action-specific authorization; production promotion also requires independent approval. Store Batch 22 projections in `software_delivery` to avoid taking authority from earlier tables.

## Consequences

The platform can standardize delivery without becoming a universal production administrator. Discovery is read-only by default, adapters start `NOT_CONFIGURED`, and incomplete evidence remains `NOT_RUN` or blocked.
