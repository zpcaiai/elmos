# Java Production Loop

```text
OIDC tenant and GitHub App installation
→ secure private runner enrollment
→ fixed commit clone
→ immutable source snapshot
→ signed reproducible JDK/build toolchain
→ baseline build/test/contract capture
→ Java health graph and target compatibility plan
→ approval
→ signed deterministic OpenRewrite recipes
→ sealed target staging
→ compile/test/contract/security/behavior verification
→ classified bounded agent repair for remaining gaps
→ full verification
→ thematic commits
→ idempotent branch/PR/checks
→ signed offline Evidence Pack
→ customer review and merge
```

## Invariants

- Source stays on the private runner by default.
- Branch names are not durable inputs; commit/tree digests are.
- Deterministic recipes precede model repair.
- Agent repair cannot delete tests, weaken assertions, disable security, broaden permissions, or bypass evidence.
- PR creation, checks, artifacts, notifications, and billing are idempotent/reconciled.
- Customer remains the merge authority.
- Commercial readiness requires three repeatable authorized repositories, not one fixture.

## Machine time and human comparison

The plan reports an autonomous eLMOS wall-clock interval with queue/execution/model/validation/transfer/retry components and confidence. Manual analysis/review/merge effort is a separate comparison and is not included in the system ETA.
