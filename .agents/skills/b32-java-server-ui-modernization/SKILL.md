---
name: b32-java-server-ui-modernization
description: Modernize JSP JSF Thymeleaf tag libraries server helpers session-bound views postbacks and Java web UI flows into a certified modern web target without losing server contracts or security.
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

## Skill 1214: JSP JSF and Thymeleaf to modern web migration

## Use this skill when

- A Java application contains JSP, JSF, Thymeleaf, tag libraries, server-side forms, postbacks, Ajax, or session-scoped view state.
- A modern React, Angular, Vue, or other exact target must coexist with or replace Java-rendered UI.
- A legacy server UI pack needs runtime, security, accessibility, visual, and representative-journey certification.

## Client-specific risks and invariants

- JSP and Thymeleaf mix scopes, tags, expressions, escaping, forms, security tags, fragments, and backend helpers.
- JSF has component tree, lifecycle, postback, converter, validator, view-state, scope, Ajax, and navigation semantics that cannot be reduced to HTML.
- Separating frontend and backend can change CSRF, session, validation, locale, error, authorization, and transaction boundaries.

## Workflow

1. Fingerprint exact Java, container, view technology, tag or component libraries, security, session, form, Ajax, locale, build, browser, and runtime capabilities.
2. Extract routes, templates, fragments, tags or component trees, scopes, expressions, forms, converters, validators, actions, postbacks, session or view state, and security tags into UI IR and backend contracts.
3. Choose an exact modern target profile and API, BFF, facade, or coexistence strategy for server actions and data.
4. Generate routes, components, forms, clients, state, tokens, adapters, and protected extension points while preserving escaping, CSRF, validation, permissions, deep links, and error contracts.
5. Run real source and target journeys including login, forms, validation, postback or Ajax, session expiry, locale, permission, and error flows.
6. Create negative, holdout, representative journey, maintenance, and legacy-view retirement evidence.

## Required repository outputs

- A directional pack for the exact Java server UI and target tuple
- UI IR plus server action, session, validation, security, route, and coexistence contracts
- Generated target, backend adapters, protected extensions, and legacy-link compatibility
- Runtime, visual, accessibility, security, form, and P0 journey evidence

## Verification

- Run the real source container and target application with equivalent users, data, locale, flags, time, and network responses.
- Verify forms, converters, validators, CSRF, permission rendering, session or view state, postback or Ajax, navigation, and errors.
- Compare server HTML or component state, target semantic tree, network, business outcomes, and governed visual baselines.
- Use independent holdout journeys not authored from the transformation implementation.

## Stop and escalate when

- JSF lifecycle, server scopes, view state, converters, custom tags, or components are unknown for a P0 journey.
- Server authorization or CSRF is removed to simplify the target.
- Backend APIs, BFFs, facades, or coexistence adapters lack owner, contract, security, and exit plan.
- The implementation is copied HTML and CSS without form, session, action, and business behavior.

## Definition of done

A complete P0 Java server UI journey runs in the exact modern target with preserved route, form, session, validation, security, locale, accessibility, visual, and business behavior, backed by holdout evidence and a bounded coexistence or retirement plan.
