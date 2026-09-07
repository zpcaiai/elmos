---
name: b32-client-modernization-factory
description: Implement and certify a directional version-specific frontend desktop or mobile modernization pack with runtime discovery typed UI interaction IR real builds browser or device execution holdout journeys and evidence.
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

## Skill 1203: Client modernization factory orchestrator

## Use this skill when

- A user asks to create or substantially expand a frontend, desktop, or mobile modernization pack.
- An existing pack generates pages or components but lacks runtime, accessibility, visual, cross-browser, device, or representative-journey evidence.
- Several Batch 32 skills must be coordinated into one production-shaped user journey.

## Client-specific risks and invariants

- Client behavior is distributed across routes, templates, state, browser or native APIs, CSS cascade, design tokens, forms, permissions, network calls, build configuration, and rendering.
- A target that compiles can still lose deep links, validation timing, focus order, session behavior, responsive layout, accessibility, analytics, or business side effects.
- Screenshot similarity alone is not proof that interaction, semantics, permissions, data binding, or device behavior is correct.

## Workflow

1. Inspect existing Batch 20-31 contracts, source and target applications, design systems, API schemas, identity flows, tests, build commands, and evidence models; write `client-packs/<pack>/certification/gap-inventory.md`.
2. Confirm accountable, maintenance, UX, accessibility, security, and product owners plus the exact source and target tuples and the first P0 journey.
3. Scaffold the pack when absent and implement static plus runtime fingerprinting before target generation.
4. Emit typed UI Interaction IR for one complete journey covering route, view, component tree, state, actions, effects, forms, API calls, permissions, tokens, and accessibility semantics.
5. Select an exact target profile and implement deterministic transformations, compatibility adapters, protected ownership, assets, and build configuration.
6. Run real source and target applications in controlled browsers or devices; capture semantic trees, network, state, screenshots, performance, accessibility, and business observations.
7. Run development, negative, holdout, and representative journeys; fix systemic discovery, IR, contract, profile, or generator failures instead of patching many target components.
8. Write privacy, lifecycle, maintainability, accessibility, economics, and certification evidence, then invoke the conservative Batch 32 gate.

## Required repository outputs

- `client-packs/<pack-key>/pack.json`, `support-matrix.json`, and `source-fingerprint/manifest.json`
- `ui-ir/model.json`, `target-profile/profile.json`, and `acceptance/acceptance-profile.json`
- `transformations/`, `compatibility/`, `baselines/`, and `corpus/{development,holdout,representative-journeys}/`
- `certification/{evidence.json,certification.json,gate-result.json}`

## Verification

- Run exact source and target builds and launch both applications with locked toolchains.
- Execute one P0 journey in the declared browser and device matrix and compare route, interaction, network, state, visual, accessibility, and business observations.
- Run `validate_client_pack.py`, `validate_ui_ir.py`, and `run_client_gate.py`.
- Verify independent holdout and representative journeys pass without weakening tests, accessibility rules, security, or visual tolerances.

## Stop and escalate when

- No owner, exact stack tuple, runnable source, target runtime, design or accessibility decision owner, or privacy-safe test data exists.
- The only strategy is template or regex replacement without typed route, state, effect, form, identity, and accessibility contracts.
- Green status requires disabling security, weakening validation, removing accessibility checks, broadening visual tolerances after failure, or replacing representative tests with snapshots only.
- Independent holdout or representative-journey evidence is unavailable for the requested claim.

## Definition of done

The pack contains executable discovery, typed UI Interaction IR, an exact target profile, deterministic transformations, real source and target runtime evidence, independent corpora, explicit limitations, and only the strongest gate-supported status.
