---
name: b32-rendering-ssr-csr-hydration
description: Migrate and verify server rendering client rendering static generation streaming hydration islands caching personalization and rendering boundaries with real browser and server evidence.
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

## Skill 1213: SSR CSR hydration and rendering-strategy migration

## Use this skill when

- A migration changes server-rendered pages, SPA rendering, static generation, streaming, islands, hydration, or personalization.
- The target looks correct but has hydration errors, duplicate requests, flashes, SEO gaps, or inconsistent server and client state.
- A target framework profile must choose an explicit rendering strategy per route or component.

## Client-specific risks and invariants

- Server and client environments differ in browser APIs, time, locale, identity, random values, and data availability.
- Hydration mismatch can discard server output, duplicate effects, lose input state, or expose personalized content.
- Rendered-content caching can cross users, tenants, locales, roles, or feature cohorts.

## Workflow

1. Inventory source rendering modes, server templates, client bootstrap, preloading, streaming, caching, personalization, browser-only APIs, and hydration boundaries.
2. Emit per-route and per-component rendering contracts including server inputs, client inputs, deterministic data, cache scope, fallback, loading, error, and hydration obligations.
3. Select target SSR, CSR, static, streaming, island, or hybrid strategies using the exact target profile and route requirements.
4. Generate server and client boundaries, serialization, data loaders, cache keys, safe browser guards, deterministic values, and protected extension points.
5. Run direct load, navigation, reload, slow network, JavaScript-disabled where required, authenticated, personalized, localized, and error scenarios.
6. Capture server HTML, accessibility tree, post-hydration DOM, console, network, state, focus, layout, SEO metadata, and business outcomes.

## Required repository outputs

- Rendering and hydration nodes in UI IR
- `transformations/rendering/` implementation and route-level rendering decisions
- Server HTML, hydration, cache, personalization, fallback, SEO, and performance evidence
- Rendering limitations, compatibility adapters, and recertification triggers

## Verification

- Require zero unapproved hydration errors for certified routes.
- Compare server HTML, semantic tree, post-hydration DOM, state, focus, inputs, effects, and network calls.
- Verify cache isolation by tenant, user, locale, permission, and feature cohort.
- Measure layout shift, startup, interaction readiness, duplicate requests, and direct-load behavior against approved budgets.

## Stop and escalate when

- A global rendering strategy is chosen without route-specific data, SEO, personalization, and interaction requirements.
- Hydration mismatches are suppressed rather than fixed or explicitly bounded.
- Rendered content or cache keys can cross users, tenants, roles, locales, or experiments.
- Certification tests client-side navigation but not direct page load or reload.

## Definition of done

Every P0 route has an explicit rendering and caching contract, secure deterministic server and client boundaries, passing direct-load and navigation behavior, and hydration, SEO, accessibility, performance, personalization, and business evidence.
