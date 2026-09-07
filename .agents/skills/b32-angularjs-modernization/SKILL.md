---
name: b32-angularjs-modernization
description: Modernize AngularJS modules dependency injection scopes digest cycles directives controllers services filters routing templates transclusion and tests into an exact certified modern target.
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

## Skill 1216: AngularJS modernization

## Use this skill when

- An AngularJS application must move to modern Angular, React, Vue, or another approved target.
- A staged hybrid or strangler migration is needed.
- Existing conversion focuses on template syntax but misses digest, scope, directive, event, and lifecycle semantics.

## Client-specific risks and invariants

- Scopes, prototypal inheritance, digest and watchers, directive compile and link, transclusion, dependency injection, and two-way binding differ materially from modern frameworks.
- Global mutable services, jQuery plugins, DOM manipulation, route resolves, filters, and event buses create hidden behavior.
- Hybrid operation can duplicate routing, state, change detection, analytics, or network side effects.

## Workflow

1. Fingerprint exact AngularJS, router, module loader, build, test, UI library, jQuery plugin, browser, and active runtime capabilities.
2. Extract modules, DI, routes, scopes, controllers, services, factories, directives, templates, bindings, watchers, events, filters, transclusion, forms, and lifecycle into UI IR.
3. Classify each capability for direct mapping, wrapper, web component, hybrid bridge, retained fragment, manual redesign, or block.
4. Implement one vertical route and component tree using the exact target profile, protected ownership, and coexistence strategy.
5. Verify digest-sensitive behavior, binding direction, directive lifecycle, event order, forms, permissions, network, visual, accessibility, analytics, and business outcomes.
6. Run negative, holdout, and representative journeys and produce a bounded hybrid-exit plan.

## Required repository outputs

- AngularJS runtime fingerprint and exact target profile
- UI IR for scopes, bindings, directives, routes, services, events, forms, and lifecycle
- Target components, adapters or hybrid bridge, tests, and protected extension points
- Hybrid risk, exit, runtime, visual, accessibility, memory, and P0 journey evidence

## Verification

- Run exact AngularJS source and target applications in the declared browser matrix.
- Verify one-way and two-way bindings, watchers, scope inheritance, directive lifecycle, transclusion, routing, forms, and event order.
- Measure duplicate network calls, events, effects, watchers, and memory leaks in hybrid mode.
- Use independent holdout routes and representative customer journeys.

## Stop and escalate when

- P0 behavior depends on undocumented DOM manipulation, jQuery plugins, directive compile or link behavior, or scope inheritance.
- Hybrid mode creates two independent authorities for route, state, identity, cache, or writes.
- The target requires disabling forms, security, accessibility, visual, or test contracts.
- Retained AngularJS fragments lack owner, support policy, or exit condition.

## Definition of done

An exact AngularJS-to-target pack migrates a complete route and business journey with modeled scope, directive, state, form, route, event, and effect behavior, real runtime evidence, independent holdout coverage, and a bounded hybrid-retirement plan.
