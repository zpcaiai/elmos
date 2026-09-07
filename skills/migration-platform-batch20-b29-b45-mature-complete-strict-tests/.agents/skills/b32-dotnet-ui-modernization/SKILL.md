---
name: b32-dotnet-ui-modernization
description: Modernize Razor ASP.NET MVC views Web Forms desktop-bound .NET UI server helpers postbacks session and legacy client assets into a certified modern web target with explicit coexistence.
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

## Skill 1215: Razor ASP.NET MVC Web Forms and legacy .NET UI migration

## Use this skill when

- A .NET application contains Razor, ASP.NET MVC views, Web Forms, server controls, ViewState, postbacks, session, or legacy JavaScript and CSS.
- The project needs a modern web target or staged strangler migration.
- Legacy .NET UI behavior must be certified beyond static view conversion.

## Client-specific risks and invariants

- Web Forms lifecycle, server controls, event validation, ViewState, postback, validation groups, UpdatePanel, and session differ from modern components.
- Razor and MVC views can depend on helpers, child actions, TempData, binders, filters, anti-forgery, bundles, and server rendering.
- Desktop-bound .NET UI can include thread affinity, commands, binding, native integrations, local resources, and accessibility constraints.

## Workflow

1. Fingerprint exact .NET, ASP.NET, IIS or host, view technology, UI libraries, bundling, auth, session, forms, build, browser, desktop, and runtime capabilities.
2. Extract routes, layouts, views, partials, helpers, controls, postback events, ViewState, binding, validation, TempData, session, filters, permissions, resources, and assets into UI IR and backend contracts.
3. Choose an exact modern web target, BFF or API strategy, coexistence boundary, rendering profile, and target ownership model.
4. Generate target routes, components, forms, clients, state, tokens, server adapters, protected extension points, and legacy compatibility.
5. Run real source and target journeys covering authentication, anti-forgery, validation, session, postback or Ajax, locale, error, navigation, and accessibility.
6. Create holdout, representative journey, retirement, maintenance, and security evidence.

## Required repository outputs

- A directional pack for the exact legacy .NET UI and target tuple
- UI IR plus server action, ViewState or state, validation, session, security, and route contracts
- Generated target application, adapters, coexistence routing, and protected target ownership
- Runtime, visual, accessibility, security, form, and representative journey evidence

## Verification

- Run exact legacy and target builds and hosts.
- Verify anti-forgery, binding, validation groups, ViewState or replacement state, session, redirects, errors, and permissions.
- Compare semantic trees, screenshots, network, storage, analytics, focus, and business outcomes.
- Run direct load, reload, back navigation, expired session, invalid postback, and negative form cases.

## Stop and escalate when

- Web Forms lifecycle or server-control behavior for a P0 journey cannot be modeled or explicitly replaced.
- Anti-forgery, authorization, session, validation, or secure storage is weakened.
- Native or desktop-only dependencies lack an approved adapter, sidecar, retained runtime, or block decision.
- Certification evidence contains only generated markup or screenshots.

## Definition of done

A real legacy .NET UI journey runs in the exact modern target with preserved security, session, form, navigation, accessibility, visual, and business behavior plus holdout evidence and a staged coexistence or exit plan.
