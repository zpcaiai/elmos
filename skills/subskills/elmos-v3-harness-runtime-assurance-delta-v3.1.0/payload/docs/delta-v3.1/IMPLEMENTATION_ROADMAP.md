# Incremental Implementation Roadmap

## P0-A — Commit and plan boundaries

Implement Result Interception/Commit and per-step finalized ExecutionPlan first. Wire both into DurableJournal, Artifact lineage and K8 invalidation.

## P0-B — Authority and ownership

Implement Canonical PermissionProfile replay, Environment/Attachment owner authority, CapabilityLease, Host-minted security context, Executor generation and Workspace lease.

## P0-C — Adapter hardening

Install protocol/version negotiation, version-isolated canonical types and Codex/DeepSeek conformance profiles.

## P1 — Ecosystem durability

Enable Skill provenance, registered durable events, typed external ingress and per-subagent model execution specs.

Every phase requires shadow mode, negative tests, replay, kill/recovery and rollback evidence before authoritative activation.
