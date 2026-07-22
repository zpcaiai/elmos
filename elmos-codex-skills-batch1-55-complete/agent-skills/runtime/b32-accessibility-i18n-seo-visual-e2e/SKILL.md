---
name: b32-accessibility-i18n-seo-visual-e2e
description: "Implement and certify accessibility localization internationalization SEO visual regression cross-browser responsive performance and end-to-end user-journey validation for client modernization packs."
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

## Skill 1221: Accessibility i18n SEO visual and E2E validation

## Use this skill when

- A client pack needs holistic customer-facing quality evidence before certification.
- Visual snapshots pass but accessibility, keyboard, locale, SEO, responsive, performance, or full-journey behavior remains uncertain.
- A target profile or release must define and enforce browser, device, locale, theme, rendering, and quality matrices.

## Client-specific risks and invariants

- Automated accessibility tools find only a subset of issues; keyboard, focus, screen reader, announcements, reading order, zoom, motion, and cognitive behavior need targeted testing.
- Localization changes layout, pluralization, dates, numbers, currency, direction, sorting, input, and content semantics.
- Visual masks, tolerances, and baseline updates can hide regressions if not governed before execution.
- SEO applies only to relevant public routes and depends on rendering, metadata, canonical links, structured data, and crawl behavior.

## Workflow

1. Load the exact acceptance profile for browser, device, locale, theme, accessibility, visual, rendering, performance, SEO, security, and P0 journeys.
2. Implement semantic-tree assertions, keyboard and focus flows, targeted assistive-technology cases, contrast, motion, zoom, error, and live-region checks.
3. Implement locale, plural, date, time, number, currency, collation, RTL, text expansion, input, fallback, and missing-key tests.
4. Implement governed visual baselines by route, state, viewport, theme, locale, and browser with pre-approved masks and tolerances.
5. Implement SEO checks for applicable routes plus responsive, cross-browser, device, performance-budget, network, console, memory, and E2E business assertions.
6. Run source and target representative journeys, classify differences, obtain owner decisions, and write evidence without auto-updating baselines.

## Required repository outputs

- `acceptance/acceptance-profile.json` and versioned quality matrix
- `baselines/{visual,accessibility,network,performance}/` with governed update history
- Cross-browser, device, locale, theme, SEO, performance, accessibility, and E2E suites
- Difference decisions and certification evidence for P0 journeys

## Verification

- Run the complete declared browser, device, locale, theme, permission, network, and rendering matrix for P0 journeys.
- Combine automated accessibility analysis with keyboard and targeted assistive-technology evidence.
- Require pre-approved visual masks and tolerances and independent review for baseline changes.
- Verify business outcomes, data, permissions, network calls, console errors, performance, accessibility, and visual state together.

## Stop and escalate when

- Accessibility certification relies only on an automated scanner.
- Visual baselines are auto-updated after a failing target run.
- Tolerances, masks, accessibility exceptions, or performance budgets are broadened after failure without approval.
- Locale, RTL, keyboard, permission, browser, device, or representative business journeys are excluded without an acceptance-profile change.

## Definition of done

The pack passes the declared accessibility, locale, visual, browser, device, rendering, performance, SEO, security, and P0 E2E matrix with governed baselines, zero critical unknowns or regressions, and owner-approved evidence.
