# Trusted Runner and Long-Task Recovery

## Execution boundary

The Runner receives an already-authorized DAG node. It does not decide scope. It enforces:

- read-only immutable source
- isolated writable worktree
- command and parameter policy
- network allowlist
- short-lived secret handles
- CPU, memory, disk, process, token, and wall-time budgets
- approval gates
- output and evidence mounts
- tamper-evident audit

## Durable execution

Run state must be server-side and independent of the browser, terminal, or IDE connection.

```text
submit → durable run ID → lease/fencing → execute → checkpoint
      ↘ reconnect/status/artifacts
```

Every stage records input hashes, policy, toolchain, worktree commit or patch, artifact hashes, side-effect journal, and next safe action. Worker loss resumes only when prerequisites still match.

## Side effects

Builds and tests are usually retryable. Database migrations, deployments, messages, payments, account changes, and external writes require idempotency keys or compensating actions. The Runner must not blindly repeat a side effect after ambiguous failure.

## Private runners

Private source, internal package registries, production-like data, native SDKs, or regulated environments may require customer-controlled runners. The control plane should pass signed work orders and receive evidence references rather than source payloads.
