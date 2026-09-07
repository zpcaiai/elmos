---
name: b32-route-navigation-deeplink
description: Migrate and verify route tables nested navigation deep links redirects guards history query and hash state not-found behavior and browser or mobile back navigation through typed contracts.
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

## Skill 1207: Route navigation and deep-link migration

## Use this skill when

- A migration changes routers, server-rendered pages, client frameworks, desktop navigation, or mobile navigation stacks.
- Deep links, redirects, route guards, history, nested layouts, or app links must remain compatible.
- Route behavior is currently inferred only from file names or templates.

## Client-specific risks and invariants

- Matching depends on precedence, constraints, base paths, locale prefixes, tenant context, flags, authentication, and server rewrites.
- A page can render correctly yet break reload, sharing, browser history, scroll restoration, mobile back stacks, or universal links.
- Redirect loops and guard ordering can create security and availability regressions.

## Workflow

1. Extract static and runtime routes, nested layouts, aliases, redirects, rewrites, guards, preloaders, query and hash state, deep links, app links, and not-found behavior.
2. Emit route contracts with precedence, parameter types, required context, permissions, rendering mode, restoration, analytics, and source traces.
3. Map contracts to the exact target router and hosting profile and generate adapters for legacy URLs or coexistence windows.
4. Implement route loading, error, permission, data, layout, and state dependencies without direct source-router coupling.
5. Run direct-load, reload, forward or back, nested, locale, tenant, unauthorized, redirect, malformed-link, and mobile or desktop back-stack tests.
6. Publish compatibility, caller, analytics, deprecation, and exit evidence for legacy routes.

## Required repository outputs

- Route and navigation nodes in UI IR
- `transformations/routes/` mappings and optional legacy URL adapters
- Deep-link, redirect, guard, history, reload, and not-found corpus
- Route compatibility and retirement report

## Verification

- Execute every P0 route by direct URL or deep link and through in-app navigation.
- Verify parameters, query, hash, locale, tenant, permission, redirect, history, reload, and state restoration.
- Run browser and applicable mobile or desktop back-stack tests.
- Compare source and target route analytics or observation contracts without user-data leakage.

## Stop and escalate when

- Route precedence, security guards, base path, or server rewrite behavior is unknown for a P0 route.
- Links can be preserved only by weakening authorization or redirect rules.
- Universal links, desktop protocol handlers, public bookmarks, or partner URLs lack an approved compatibility plan.
- Legacy adapters have no owner or exit condition.

## Definition of done

P0 routes, deep links, guards, redirects, history, reload, and not-found behavior are typed, generated for the exact target router, verified at runtime, and covered by a bounded compatibility and retirement plan.
