---
name: evidence-and-audit-model
description: Create or review immutable ELMOS evidence, append-only audit events, content hashes, artifact references, Agent activity summaries, validation policies, evidence packs, and report traceability. Use for scan, build, test, Recipe, Agent, API, database, security, approval, PR, or delivery results.
---

# Evidence and Audit Model

## 证据协议

Record evidenceId, tenant, MigrationRun and StepRun, type, producer identity/version, source and target commit, time, status, summary, artifact reference, SHA-256 content hash, schema version, and correlation ID.

Use PASS, WARN, FAIL, NOT_RUN, and INCONCLUSIVE exactly. Never treat NOT_RUN or INCONCLUSIVE as PASS and never overwrite an Evidence record. Correct it by appending a replacement version.

For Coding Agent changes, record provider, model, Skill version, problem summary, tool actions, changed files, patch hash, commands, credits, stop reason, and validation. Do not store private chain-of-thought.

## 审计与成功判定

Append actor, action, resource, before/after hash, time, request/runner, policy decision, and result. Do not delete audit records. Validate artifact hashes on read.

Let ValidationPolicy combine build, test baseline, API compatibility, vulnerability threshold, approvals, FAIL evidence, and required NOT_RUN checks. Do not let a single tool or Agent decide success.

## 执行步骤

1. Identify the claim and the exact tool output that supports it.
2. Store raw/sanitized artifacts and calculate the content hash.
3. Create immutable Evidence and an audit event in the same durable workflow transaction where required.
4. Reference Evidence IDs from Steps, reports, PR checks, and remaining risks.
5. Generate machine-readable evidence and mark skipped checks explicitly.
6. Test mutation detection, required-evidence gaps, and NOT_RUN behavior.

## 交付与失败

Prepare report, plan, risk register, validation evidence, Agent activity, SBOM, summary, and rollback plan in later delivery batches. On missing or unverifiable proof, set NOT_RUN or INCONCLUSIVE, retain logs, and block a success claim.

