# Runbook — Invocation-Scoped Capability Lease

## Preflight

1. Confirm base package `3.0.0`, Delta manifest/hash and migration state.
2. Confirm provider profile and exact capability negotiation result.
3. Confirm tenant/RLS, policy bundle, Environment Authority, executor/workspace generation and journal/outbox health.
4. Run schema, unit, negative, replay and adapter conformance tests.

## Rollout

- Start in observe-only mode and emit comparison evidence without changing authoritative state.
- Enable shadow decisions, then canary by tenant/repository/adapter version.
- Promote only when all hard gates show zero authority widening, zero replay divergence and zero stale commit acceptance.
- Record activation revision in Goal Revision Sets and invalidate stale completion certificates.

## Incident actions

- **Authority or lease leak:** revoke affected invocation/environment leases, fence executor generations and disable the adapter profile.
- **Result commit divergence:** stop publication/model ingress, retain raw/effective artifacts and replay with the pinned interceptor chain.
- **Replay/unknown event failure:** refuse resume, materialize the minimal event bundle and apply only a signed upgrader.
- **Workspace conflict:** freeze writes, compare owner/generation records and perform explicit takeover or rollback.
- **Version incompatibility:** quarantine the provider version; never add an unreviewed compatibility alias in core contracts.

## Rollback

Disable the extension activation feature flag, drain in-flight authoritative transitions, run reconciliation, then use the Delta uninstaller. Do not remove evidence required to interpret already committed executions.

## Completion

This runbook confirms only extension-local health. K8 alone evaluates Goal completion.
