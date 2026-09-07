---
name: b32-component-template-view-migration
description: "Migrate server templates views component trees slots content projection conditional rendering lists events lifecycle and composition into target components through typed UI contracts and runtime verification."
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

## Skill 1208: Component template and view migration

## Use this skill when

- Server templates, legacy views, or client components must be converted into a modern component framework.
- Existing generation creates static markup but not component behavior, ownership, slots, lifecycle, or event contracts.
- Repeated UI patterns need extraction into reusable target components.

## Client-specific risks and invariants

- Template syntax can hide data scope, escaping, conditionals, iteration identity, server helpers, partials, and implicit lifecycle.
- Component extraction can change semantic structure, event propagation, focus, CSS selectors, analytics hooks, or test locators.
- Lists require stable identity; index keys can corrupt component state and user input.

## Workflow

1. Inventory templates, partials, layouts, tag libraries, helpers, components, slots, projection, events, and lifecycle hooks.
2. Emit view and component IR with inputs, outputs, slots, conditionals, keyed collections, events, effects, semantic roles, styles, permissions, and source traces.
3. Identify reusable component candidates and intentional one-off views and obtain design-system or UX decisions before consolidation.
4. Generate target components, layout shells, slots, event handlers, ownership metadata, and protected extension points using the target profile.
5. Preserve escaping, sanitization boundaries, analytics identifiers, focus behavior, test contracts, and stable list identity.
6. Run build, component, interaction, visual, accessibility, memory, and representative-journey tests.

## Required repository outputs

- View and component nodes in UI IR
- `transformations/components/` mappings and generated target components
- Component ownership, reuse, slot, event, list-identity, and extension manifests
- Component, interaction, visual, accessibility, and representative-page evidence

## Verification

- Render source and target components with equivalent inputs, state, slots, locale, theme, data, and permissions.
- Compare semantic DOM or accessibility tree, events, focus, lifecycle, network, and approved visual baselines.
- Verify list identity, escaping, sanitization, analytics, cleanup, and test locators.
- Run representative pages and journeys rather than isolated component stories only.

## Stop and escalate when

- Target generation needs raw HTML insertion without a reviewed sanitization contract.
- Component consolidation changes business rules, event order, permissions, analytics, or layout ownership without approval.
- Stable list identity, lifecycle cleanup, source data scope, or slot semantics is unknown.
- Certification evidence contains only static screenshots or isolated stories.

## Definition of done

The migrated component and view graph is typed, source-traceable, reusable where approved, protected against markup and lifecycle regressions, and verified in real pages across interaction, visual, accessibility, network, and business contracts.
