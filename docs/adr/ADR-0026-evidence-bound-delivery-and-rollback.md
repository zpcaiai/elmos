# ADR-0026: Evidence-bound delivery, SCM collaboration and rollback

- Status: Accepted
- Date: 2026-07-21

## Decision

A content-addressed Delivery Snapshot is the single read model for technical reports, executive summaries, risks, SCM delivery, evidence packs, rollback and acceptance. JSON is authoritative; Markdown and escaped HTML are projections and cannot edit evidence.

GitHub pull requests and GitLab merge requests are Draft by default, never auto-merge and never force-push. Check publications bind to the exact HEAD SHA and become stale when it changes. GitHub annotations are published in batches of at most 50, matching the GitHub Checks API limit. GitLab uses external status checks only when the detected tier supports them and otherwise publishes a commit-status fallback.

Evidence packs are deterministic tar.zst archives. The manifest records SHA-256 for every included artifact and is signed with Ed25519. Secrets, credentials and full source archives are rejected. Runtime signing requires an externally supplied signing key; absent configuration fails closed.

Rollback plans cover code, database, cache, messages, deployment and traffic. Destructive database changes require verified restore or roll-forward options; incompatible cache changes require dual read. RTO and RPO must be supplied by an owner and are never invented. Delivered, Accepted, Merged, Released and Closed remain distinct HEAD-bound lifecycle states.

## Consequences

SCM plans and check payloads can be generated offline, but creating a real PR/MR, publishing a check, attesting an artifact or executing rollback requires configured provider credentials and live evidence.
