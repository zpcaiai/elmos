---
name: b32-react-angular-vue-target-profile
description: Create and certify exact React Angular or Vue target profiles covering versions build rendering state forms styling design system API clients identity i18n accessibility testing browser device and maintenance policies.
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

## Skill 1217: React Angular and Vue target profile

## Use this skill when

- A client pack needs an exact reusable target implementation profile.
- Teams select target libraries ad hoc or use floating versions without compatibility evidence.
- Multiple packs need a common build, architecture, testing, security, accessibility, and lifecycle baseline.

## Client-specific risks and invariants

- A target framework name does not determine router, renderer, state, forms, styling, design system, cache, identity, i18n, tests, browser support, or deployment.
- Provider combinations can be individually valid but incompatible or operationally unmaintainable together.
- A target profile can become unsupported while certified packs still depend on it.

## Workflow

1. Inspect product architecture, team skills, deployment, browser and device matrix, accessibility target, design system, API contracts, security, SLOs, and LTS requirements.
2. Define exact framework, language, runtime, build, package manager, router, rendering, state, forms, styling, design system, data cache, identity, i18n, telemetry, and test versions.
3. Record lifecycle, maintenance owner, approved dependencies, security policies, browser and device matrix, performance budgets, and compatibility adapters.
4. Implement a reference shell with route, component, form, state, API, identity, theme, i18n, accessibility, loading, error, empty, permission, and test examples.
5. Build, start, test, scan, benchmark, and package the profile in declared environments.
6. Publish versioned evidence, upgrade policy, deprecation plan, compatibility matrix, and recertification triggers.

## Required repository outputs

- `target-profile/profile.json` conforming to the Batch 32 schema
- A production-shaped reference shell and exact lock files
- Browser, device, accessibility, security, performance, rendering, and test profiles
- Lifecycle, maintenance, upgrade, deprecation, and supply-chain evidence

## Verification

- Install from a clean environment using exact lock files and immutable build images.
- Run build, startup, route, state, form, API, identity, i18n, accessibility, visual, cross-browser, performance, security, and supply-chain tests.
- Verify no floating versions, duplicate route or state authorities, conflicting renderers, or unowned dependencies.
- Prove at least one real client pack consumes the profile without source-framework coupling.

## Stop and escalate when

- Exact versions, maintenance owner, browser or device support, security, accessibility, or lifecycle is undefined.
- The profile uses latest or broad floating ranges.
- Providers create duplicate routing, rendering, state, auth, cache, or form authorities.
- Certification depends only on a sample counter or static component gallery.

## Definition of done

The exact target profile is reproducible, maintained, security and accessibility reviewed, backed by a production-shaped reference shell and quality matrix, and successfully consumed by at least one real migration pack.
