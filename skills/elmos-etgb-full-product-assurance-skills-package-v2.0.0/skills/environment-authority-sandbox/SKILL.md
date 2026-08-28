---
name: environment-authority-sandbox
description: Enforce Environment-owned or Attachment-owned tool authority, least privilege, hidden-test isolation, network and secret policy, leases, and fencing.
---

# Environment Authority and Sandbox

## Security model

Authority belongs to the concrete Environment or Attachment that owns a tool request. It is never inherited from a Thread-global, Session-global or unrelated resumed-task policy. Every request binds:

```text
authority_id + environment_id + owner_id + tenant_id
+ role + fencing_token + expiry
```

Failure to resolve any binding is a deny, not a fallback.

## Roles

- `transform-worker`: source/public tests and target workspace; no hidden-test access.
- `generation-worker`: requirement inputs and target workspace; no hidden-test access.
- `validation-worker`: read-only target, hidden-test execution and evidence staging; no source mutation.
- `evidence-worker`: content-addressed evidence and redaction only.
- `release-worker`: score and sealed evidence read access; no target mutation.

## Authorization workflow

1. Load the exact authority snapshot captured when the Environment/Attachment was attached.
2. Verify digest, expiry, revocation, owner, tenant and current fencing token.
3. Verify capability such as `harness.build` or `process.execute`.
4. Canonicalize paths and reject traversal, unsafe symlinks and writes outside granted roots.
5. Enforce deny-by-default network or exact allowlist.
6. Resolve only named secret references; never expose raw secret inventory.
7. Enforce hidden-test read/write/execute flags independently.
8. Log the decision without logging secret values or hidden-test content.

## Lifecycle

A policy refresh creates a new authority version; it does not retroactively widen a live attachment. Resume must reacquire a lease and a higher fencing token. Revocation prevents further tool calls, checkpoint writes, evidence publication and usage charges.

## Required negative tests

- owner/environment/tenant mismatch;
- stale fencing token and expired lease;
- path traversal, symlink escape and archive traversal;
- secret-scope escalation;
- non-allowlisted DNS/IP including redirect targets;
- hidden-test read and write attempts by generation workers;
- cross-tenant artifact, cache and trace access;
- authority snapshot drift after Session resume.

## Artifacts and code

Use `schemas/environment-authority.schema.json`, `integrations/policy/`, and `etgb/policy.py`. The Python implementation is a reference policy evaluator; production enforcement must also exist at the executor/tool boundary, not only in orchestration code.

## Hard gate

Any authority bypass, hidden-test leak, secret exposure, tenant crossing or stale-fence side effect is P0 and non-waivable.
