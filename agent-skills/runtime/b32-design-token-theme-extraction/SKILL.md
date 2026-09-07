---
name: b32-design-token-theme-extraction
description: "Extract normalize migrate and verify design tokens themes typography spacing color responsive rules assets CSS cascade and design-system contracts without flattening them into copied styles."
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

## Skill 1206: Design token theme and design-system extraction

## Use this skill when

- A migration must preserve brand, layout, responsive behavior, high-contrast, dark mode, or multiple themes.
- Styles are spread across CSS, preprocessors, inline styles, component libraries, server templates, and runtime theme configuration.
- The target needs a reusable token or design-system implementation rather than copied legacy CSS.

## Client-specific risks and invariants

- Computed styles can look correct at one viewport while losing cascade, theme switching, contrast, focus, localization, or responsive behavior.
- Value clustering can create false tokens when the source contains intentional exceptions or context-dependent values.
- Font licensing, loading, fallback, and text metrics affect layout and cannot be treated as decorative metadata.

## Workflow

1. Inventory style sheets, preprocessors, modules, utilities, inline styles, themes, assets, fonts, media queries, motion, and high-contrast behavior.
2. Capture computed styles and layout metrics for representative components, states, viewports, locales, themes, and browsers.
3. Build a typed token model for semantic color, typography, spacing, radius, elevation, motion, breakpoint, z-index, icon, and asset roles with source evidence.
4. Classify values as reusable token, component token, intentional exception, generated value, or unknown while preserving cascade and specificity obligations.
5. Generate target tokens, theme adapters, component mappings, asset manifests, and protected design-system extension points.
6. Run visual, contrast, focus, responsive, font-loading, reduced-motion, and theme-switch tests across the acceptance matrix.

## Required repository outputs

- Design-token and theme nodes in UI IR with source traces
- `transformations/styling/` mappings and target design-system adapters
- `baselines/visual/` and `baselines/accessibility/` evidence
- Font, icon, image, license, responsive, and intentional-exception manifests

## Verification

- Validate token uniqueness, semantic naming, source trace, contrast, and target consumption.
- Run visual comparisons across themes, locales, viewports, component states, and browsers.
- Verify focus indication, reduced motion, font fallback, asset integrity, and layout stability.
- Confirm target components consume tokens rather than duplicating literals beyond approved exceptions.

## Stop and escalate when

- Font, icon, image, or design-system licensing and ownership is unknown.
- The transformation copies all computed styles without preserving design intent or responsive behavior.
- Contrast, focus, theme, or localization regressions are required for visual similarity.
- Visual tolerances or masks are broadened after failures without UX and accessibility approval.

## Definition of done

The pack contains a typed source-traceable token and theme model, target design-system mappings, asset and license evidence, responsive and theme verification, and no unapproved visual or accessibility regression in P0 journeys.
