---
name: b32-client-identity-permission-flags
description: "Migrate client authentication state sessions tokens claims permissions route and component guards tenant context feature flags experiments and privacy-sensitive telemetry without relying on client checks for server security."
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

## Skill 1212: Client identity permission and feature-flag migration

## Use this skill when

- A migration changes identity SDKs, token or cookie storage, route guards, permission rendering, tenant context, feature flags, or experiments.
- The target risks exposing restricted content or actions even though server authorization remains authoritative.
- Feature and experiment behavior must stay compatible during coexistence, canary, or rollback.

## Client-specific risks and invariants

- Client authorization is a usability control, not a substitute for server enforcement, but incorrect rendering can leak data, metadata, or actions.
- Token storage, refresh, logout, cross-tab synchronization, tenant switching, and session expiry are security-sensitive.
- Feature flags, experiments, remote configuration, and cohorts can change routes, components, calls, analytics, and cached content.

## Workflow

1. Inventory identity SDKs, login and logout, tokens or cookies, refresh, expiry, tenant and role state, guards, permission components, flags, experiments, analytics, and privacy controls.
2. Emit identity, session, principal, claim, permission, tenant, flag, cohort, storage, and audit contracts with server-policy references.
3. Select exact target identity and feature-management profiles and generate providers, guards, safe storage, refresh, logout, tenant switching, and rollout adapters.
4. Ensure server authority remains intact and the target safely handles denied, expired, revoked, switched-tenant, offline, and partial-profile states.
5. Run anonymous, valid, expired, revoked, wrong-role, cross-tenant, feature-on, feature-off, cohort, logout, cross-tab, and rollback tests.
6. Compare rendered content, routes, network calls, storage, cache, analytics, audit, and business side effects.

## Required repository outputs

- Identity, session, permission, tenant, feature, experiment, and storage nodes in UI IR
- `transformations/auth/` plus target identity and feature-management integration
- Token or cookie, refresh, logout, tenant-switch, cohort, analytics, and rollback policies
- Security, privacy, and P0 permission evidence

## Verification

- Verify server authorization separately from client visibility.
- Test expiry, refresh, revocation, logout, cross-tab state, tenant switching, route and component guards.
- Verify denied or switched users do not request, render, store, cache, or log restricted data.
- Test flag and experiment consistency across routes, rendering, network, analytics, canary, and rollback.

## Stop and escalate when

- The target stores tokens or sensitive profile data in a weaker location without security approval.
- Client checks are proposed as a replacement for server authorization.
- Cross-tenant state, cache, storage, screenshot, or analytics isolation cannot be demonstrated.
- Feature or experiment ownership, exposure, privacy, compatibility, or rollback is unknown.

## Definition of done

Identity, session, permission, tenant, flag, and experiment behavior is explicitly contracted, target storage and lifecycle are approved, server authority is preserved, and critical denial, expiry, revocation, tenant, rollout, and privacy scenarios pass without leakage.
