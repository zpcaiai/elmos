---
name: b32-state-management-lifecycle
description: Migrate local shared server persisted derived and asynchronous client state plus lifecycle and effect semantics without stale data leaks invalid ordering or duplicated side effects.
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

## Skill 1209: State management and client lifecycle migration

## Use this skill when

- A migration changes state libraries, component lifecycle, desktop view models, mobile state, or client and server data boundaries.
- The target initially renders correctly but loses updates, cleanup, persistence, offline, or concurrent-request behavior.
- State behavior must be represented independently of source framework syntax.

## Client-specific risks and invariants

- Local UI state, global business state, server cache, URL state, form state, persistent storage, and derived state have different ownership and invalidation rules.
- Lifecycle differences can duplicate requests, subscriptions, timers, analytics, or mutations and can leak resources.
- Async races, stale responses, optimistic updates, rollback, offline queues, and cross-tab or window synchronization can alter business behavior.

## Workflow

1. Inventory state stores, view models, component state, URL state, persistent storage, server-state caches, selectors, subscriptions, effects, timers, workers, and lifecycle hooks.
2. Emit state, action, transition, effect, cleanup, persistence, conflict, and ownership contracts in UI IR.
3. Classify state as local, shared, server-owned, persisted, derived, optimistic, ephemeral, offline, or security-sensitive and select an exact target strategy.
4. Generate reducers, stores, hooks, services, view models, cache policies, cancellation, conflict handling, and extension points using deterministic mappings.
5. Implement race, cancellation, stale-response, optimistic rollback, reload, offline, multi-tab, process-death, and cleanup tests where applicable.
6. Measure effect counts, network calls, transitions, memory, persistence, and business results in source and target journeys.

## Required repository outputs

- State, action, transition, effect, cleanup, and lifecycle nodes in UI IR
- `transformations/state/` mappings and target state implementation
- State ownership, persistence, invalidation, cancellation, conflict, and offline policies
- State-transition, effect-count, cleanup, memory, and P0 journey evidence

## Verification

- Replay deterministic state-machine scenarios with controlled clock, network, and external responses.
- Verify no duplicate effects, subscriptions, requests, analytics, or mutations.
- Test reload, navigation, optimistic rollback, cancellation, stale response, cleanup, offline, and cross-context behavior.
- Run memory and resource-leak checks for long-lived views, stores, sessions, or mobile processes.

## Stop and escalate when

- State ownership or source of truth is ambiguous for a P0 value.
- Security-sensitive state must be moved to weaker client storage without an approved policy.
- Green status requires ignoring races, duplicate effects, cleanup failures, stale data, or offline conflicts.
- A target state provider is selected without matching lifecycle, persistence, concurrency, and offline requirements.

## Definition of done

Client state and lifecycle behavior is represented as typed contracts, generated with an exact target strategy, and verified for transitions, effects, cleanup, races, persistence, offline behavior, and P0 outcomes with no critical duplicate or stale-state regression.
