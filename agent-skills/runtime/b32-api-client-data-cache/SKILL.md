---
name: b32-api-client-data-cache
description: "Migrate client API contracts transport authentication retries cancellation pagination streaming server-state caching invalidation optimistic updates offline behavior and generated clients."
---

## Operating mode

Work in the repository. Inspect existing Batch 20-31 contracts, client applications, target profiles, API and identity contracts, evidence models, build commands, browser or device automation, and tests before editing. Implement the smallest production-shaped vertical user journey that satisfies this skill; do not stop at design notes when executable discovery, typed IR, transformations, target code, runtime tests, and evidence can be added.

Read these shared contracts first:

- `../../../docs/batch32/IMPLEMENTATION_CONTRACT.md`
- `../../../docs/batch32/QUALITY_GATES.md`
- `../../../docs/batch32/REPOSITORY_LAYOUT.md`
- `../../../docs/batch32/CLIENT_MATRIX.md`
- `../../../docs/batch32/VERSION_LIFECYCLE.md`
- `../../../docs/batch32/ACCESSIBILITY_VISUAL_POLICY.md`
- `../../../docs/batch32/DATA_PRIVACY_POLICY.md`

Use the supplied helpers where applicable:

- `python3 scripts/batch32/scaffold_client_pack.py ...`
- `python3 scripts/batch32/validate_client_pack.py ...`
- `python3 scripts/batch32/validate_ui_ir.py ...`
- `python3 scripts/batch32/run_client_gate.py ...`

## Global constraints

- Treat every client modernization pack as directional, exact, source-stack/version and target-stack/version specific, and independently certified. A reverse route or another target profile is a separate pack.
- Capture exact framework, language, runtime, build tool, package manager, router, rendering, state, forms, styling, design system, API client, identity, i18n, testing, browser, device, and deployment facts. Never use `latest` or claim a framework family from one tuple.
- Run real source and target builds and real applications in approved browsers, emulators, simulators, or devices. Static parsing, generated markup, screenshots, or component stories alone are not certification evidence.
- Parse behavior into typed UI Interaction IR and explicit route, state, effect, form, API, identity, rendering, design-token, and accessibility contracts. Do not implement complex migration as regex or template-string replacement.
- Preserve business outcomes, route and deep-link behavior, state ownership, lifecycle and cleanup, form binding and validation, authorization, tenancy, network contracts, rendering, accessibility, localization, visual hierarchy, responsive behavior, analytics, privacy, and error contracts.
- Keep development, negative, holdout, and representative-journey corpora physically separate. Do not author transformations or visual tolerances from holdout cases.
- Prefer deterministic mappings and certified adapters. Model-generated components, types, styles, or tests are candidates and must pass the same build, runtime, accessibility, visual, security, cross-browser or device, and test-integrity gates.
- Record unsupported, conditional, lossy, and unknown behavior explicitly. Never hide it with `any`, broad suppressions, disabled validation or authorization, ignored hydration errors, auto-updated baselines, widened visual masks, or removed tests.
- Fix repeated failures in discovery, UI IR, contracts, target profiles, transformations, or generators instead of patching many target components independently.
- Protect customer-owned target code and design assets. Generated, shared, manual, generated-once, and protected ownership must be explicit before regeneration.
- Apply privacy minimization to production traffic, screenshots, logs, analytics, model context, and test data. Never persist credentials or unnecessary personal, payment, health, or customer content.
- Run the narrowest relevant tests first, then independent holdout and representative journeys, and finally the conservative Batch 32 gate before making release claims.

## Skill 1211: API client data-fetch and cache migration

## Use this skill when

- A migration changes HTTP libraries, generated clients, GraphQL, WebSocket, server-state libraries, or caching strategies.
- The target renders correctly but performs duplicate calls, stale reads, unsafe retries, or different error behavior.
- Client behavior must coordinate with API, data, identity, transaction, or compatibility contracts.

## Client-specific risks and invariants

- Transport errors, business errors, cancellation, timeout, retry, authentication refresh, pagination, streaming, and partial data require distinct contracts.
- Automatic retries can duplicate non-idempotent writes and cache keys can cross tenants, users, roles, locales, or feature cohorts.
- Generated clients can silently change decimal, date, enum, null, missing, serialization, and error semantics.

## Workflow

1. Inventory HTTP, GraphQL, WebSocket, SSE, IPC, native bridge, generated clients, auth interceptors, retries, cache keys, invalidation, optimistic updates, pagination, and offline queues.
2. Emit operation, transport, error, cancellation, retry, cache, mutation, consistency, and source-trace contracts.
3. Select an exact target data-access profile and generate typed clients, serializers, interceptors, stable cache keys, cancellation, and error adapters.
4. Protect idempotency, tenant and user scope, token refresh, invalidation, pagination, streaming, offline reconciliation, and optimistic rollback.
5. Run controlled network replay for success, error, timeout, retry, cancellation, stale cache, auth refresh, offline, and reconnect cases.
6. Record canonical requests, responses, call counts, cache events, transitions, business outcomes, and duplicate side effects.

## Required repository outputs

- API, transport, cache, retry, mutation, and consistency nodes in UI IR
- `transformations/api-client/` plus target clients and cache implementation
- Generated-client, serializer, authentication, retry, pagination, streaming, and cache manifests
- Network, cache, state, and P0 business evidence

## Verification

- Compare canonical requests, responses, headers, errors, pagination, streaming, cancellation, and timeout behavior.
- Verify non-idempotent operations are not retried without an approved idempotency contract.
- Test cache isolation, invalidation, stale windows, optimistic rollback, auth refresh, offline, and reconnect behavior.
- Use the exact API or an approved deterministic replay environment.

## Stop and escalate when

- The target requires broad retries for non-idempotent operations.
- Cache keys omit tenant, user, role, locale, feature, or request dimensions required by the contract.
- Generated clients lose decimal, date, enum, null, missing, or error semantics.
- External APIs cannot be safely replayed or virtualized for representative tests.

## Definition of done

The target client preserves API and error contracts, cancellation, retry safety, pagination, streaming, cache isolation and invalidation, optimistic and offline behavior, with runtime network and business evidence for all P0 journeys.
