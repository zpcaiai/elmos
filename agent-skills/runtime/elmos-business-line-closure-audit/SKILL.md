---
name: elmos-business-line-closure-audit
description: Audit ELMOS business lines and functional modules as complete user journeys, distinguish intentional fail-closed boundaries from missing implementation, repair verified repository-local gaps, and produce evidence-bounded results. Use for whole-project feature audits, missing-function reviews, logic-closure requests, release-readiness reviews, or when green module tests may hide disconnected UI, API, service, persistence, workflow, evidence, or recovery paths.
---

# ELMOS Business Line Closure Audit

## Objective

Turn a broad “check every feature and close the gaps” request into a bounded, repeatable audit. Verify behavior from entry point to terminal outcome; do not equate file presence, a green build, or an intentionally blocked external action with business completion.

## Required context

Read `AGENTS.md`, the root `README.md`, the root `Makefile`, the Maven reactor, application package manifests, deployment topology, and the narrowest domain Skill before editing. Preserve unrelated worktree changes and existing `NOT_RUN`, `UNKNOWN`, `INCONCLUSIVE`, and `NOT_CERTIFIED` evidence states.

## Closure model

Represent every business journey with these links:

```text
actor/entry
→ input and authorization
→ API or command contract
→ domain decision or execution
→ durable state or explicit non-persistence
→ evidence and observability
→ terminal success, failure, blocked, cancel, retry or reconciliation path
→ user-visible next action
```

A journey is closed only when every applicable link exists and the status shown to the user matches the real terminal state.

## Workflow

1. Inventory business lines from applications, engines, modules, routes, CLIs, UI navigation, deployment services and authoritative documentation.
2. Map P0 journeys and exact owners. Treat Migration Packs, Product batches and Project Synthesis namespaces separately.
3. Run the repository-native baseline before diagnosing gaps:

```bash
make verify
make production-readiness-check
```

4. Trace each entry through real code. Confirm request validation, tenant and resource authorization, idempotency, state transitions, persistence or declared in-memory scope, external adapters, evidence, errors, cancellation, reconciliation and recovery.
5. Classify every suspected gap before editing:
   - `IMPLEMENTATION_GAP`: a promised in-scope path is absent or disconnected.
   - `CONTRACT_DRIFT`: UI, API, CLI, documentation or deployment values disagree.
   - `OPERABILITY_GAP`: service discovery, configuration, health, startup or dependency wiring breaks a valid path.
   - `TEST_GAP`: a critical path is implemented but lacks a meaningful negative or integration check.
   - `INTENTIONAL_BOUNDARY`: the repository explicitly fails closed because approval, Runner, provider, customer, production or independent evidence is unavailable.
   - `EXTERNAL_GATE`: implementation is ready locally but real external execution remains `NOT_RUN`.
6. Repair only verified repository-local gaps. Reuse existing aggregates, ports, routes and validators; do not create parallel business models.
7. Add the smallest regression test or conservative validator that would have detected each repair.
8. Re-run narrow tests, then the relevant full gate. Keep skipped and unavailable checks visible.

## Audit matrix

For every line, record:

- actor and business outcome;
- UI, API, CLI or event entry;
- owning application, module and engine;
- state owner and persistence scope;
- authorization and tenant boundary;
- idempotency, retry, cancel and reconciliation behavior;
- evidence and external-operation status;
- runnable verification command;
- current classification and repair status.

Do not mark a line complete solely because a controller test, schema validator or static Skill check passes.

## Required negative checks

Include applicable cases:

- missing, empty, invalid and conflicting input;
- duplicate idempotency key with different payload;
- cross-tenant or wrong-resource access;
- stale, revoked, altered or unapproved evidence;
- unavailable dependency and timeout;
- unknown external result requiring reconciliation;
- cancellation before and after terminal state;
- UI fallback that must not claim live data;
- service hostname or port valid on the host but invalid inside a container;
- skipped external evidence represented as `NOT_RUN`, never success.

## Repair rules

- Prefer a vertical user journey over disconnected scaffolding.
- Keep client and server validation authority explicit.
- Use typed contracts and machine-readable reason codes.
- Make fallbacks disclose their source.
- Add capability discovery instead of assuming an adapter or Runner exists.
- Preserve fail-closed boundaries for production, financial, security, provider and customer side effects.
- Do not weaken tests, permissions, network isolation, evidence requirements or certification gates.

## Verification evidence

Report exact commands and results for Java, .NET, Python, frontend, Web, Project Synthesis and production-operability checks that actually ran. Separate:

- local engineering evidence;
- generated/build/startup evidence;
- authenticated provider or customer evidence;
- independent certification evidence.

Only the applicable conservative gate may raise a certification state.

## Stop conditions

Stop and report `BLOCKED` instead of guessing when a repair requires new production authority, real credentials, a customer decision, an irreversible external action, or a security boundary that cannot be enforced. Do not implement an intentional blocked adapter as a fake success path.

## Completion report

Return:

1. business lines audited and their closure state;
2. verified gaps and root causes;
3. implemented files and behavior;
4. exact test and gate results;
5. intentional boundaries and external `NOT_RUN` items;
6. remaining owner- or environment-dependent work.
