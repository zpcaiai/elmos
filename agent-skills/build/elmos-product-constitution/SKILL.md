---
name: elmos-product-constitution
description: Enforce ELMOS product boundaries, modular-monolith architecture, deterministic-tool priority, evidence requirements, sandbox separation, enterprise tenant controls, commercial operations boundaries, and Batch scope. Use before designing, implementing, or reviewing any ELMOS platform change or ADR.
---

# ELMOS Product Constitution

## 适用场景

Use for every ELMOS control-plane, execution-plane, validation, delivery, or architecture decision. Do not use this Build Skill to modify or migrate a customer repository.

## 目标与输入

Take the request, affected modules, current batch, existing ADRs, and proposed external effects. Classify the change before editing:

- Control plane: accept requests, persist state, dispatch work, manage approval, expose results.
- Execution plane: run untrusted customer code only in an isolated Workspace.
- Validation: compile, test, contract, security, and quality evidence.
- Delivery: publish reviewable artifacts and PRs without automatic merge.

## 强制规则

1. Keep the MVP on GitHub, Maven, Java 8/11, Spring Boot 2.x, Java 21, Spring Boot 3.x, Docker sandbox, OpenRewrite, build/test, and PR delivery.
2. Prefer OpenRewrite, then compile/test, then error classification, then a constrained Coding Agent.
3. Never run Maven, Gradle, shell, OpenRewrite, customer tests, customer applications, or Coding Agents inside the control-plane process.
4. Never let an LLM or in-memory graph own the durable MigrationRun state.
5. Treat evidence as immutable; treat NOT_RUN and INCONCLUSIVE as non-passing.
6. Never auto-merge, disable security, delete failing tests, or hide remaining risk.
7. From Batch 9 onward, every customer object and side effect carries server-derived Organization, actor/workload, policy version, correlation, usage, audit and retention context.
8. Security policy always outranks entitlement. Pricing, entitlement, quota, internal cost and formal accounting are distinct concepts.
9. Keep CRM, payment collection, tax, formal invoicing, revenue recognition and full ERP outside ELMOS behind integration Ports.

## Batch 9 and 10 routing

For enterprise controls, use the B016–B025 Build Skills covering tenant isolation, SSO, authorization, private Runner, Secret Broker, Model Gateway, usage ledger, audit, retention and offline deployment.

For commercial operations, use the B026–B035 Build Skills covering product entitlement, order fulfillment, onboarding, project cockpit, SLA, support, marketplace assets, implementation knowledge, customer success and closed-loop analytics.

## 执行步骤

1. Read the request, module POMs, contracts, tests, and relevant ADRs.
2. State architecture ownership, data owner, trust boundary, batch membership, and validation strategy.
3. Reject or narrow changes that cross the control/execution boundary or add premature infrastructure.
4. Implement through domain/application Ports and isolated adapters.
5. Add or update an ADR for a material decision.
6. Run focused tests, then repository verification.
7. Report modified behavior, commands, evidence, skipped checks, and remaining risks.

## 验收与证据

Require a scoped diff, passing verification commands, architecture-test coverage, an ADR path when applicable, and machine-readable evidence for side effects. On failure, preserve logs, classify the failure, avoid success claims, and request human review for ambiguous business semantics.
