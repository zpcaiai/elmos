---
name: b32-mobile-crossplatform
description: Migrate native or legacy mobile applications into native or cross-platform targets with navigation lifecycle background offline secure storage permissions deep links push device APIs accessibility store and rollout contracts.
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

## Skill 1220: Mobile and cross-platform client migration

## Use this skill when

- An iOS, Android, hybrid, or legacy mobile app needs modernization or convergence on a cross-platform target.
- The migration must preserve navigation, deep links, lifecycle, background work, push, offline data, secure storage, and device permissions.
- A mobile pack needs real device or emulator, signing, store, accessibility, privacy, and staged-rollout evidence.

## Client-specific risks and invariants

- Lifecycle, background execution, process death, navigation stacks, links, push, secure storage, biometrics, permissions, and offline sync differ by OS and version.
- Cross-platform frameworks need explicit platform adapters for capabilities that do not share identical native semantics.
- Store signing, entitlements, privacy disclosures, rollout, crash reporting, upgrade, and local data migration are part of the contract.

## Workflow

1. Fingerprint source platforms, OS versions, SDKs, build, signing, packages, navigation, lifecycle, storage, network, offline, push, links, device APIs, permissions, accessibility, analytics, and release configuration.
2. Emit mobile UI, navigation, lifecycle, background, storage, permission, notification, device, sync, and platform-extension contracts in UI IR.
3. Select exact native or cross-platform target profiles and classify shared, platform-specific, retained, adapter, local-agent, manual, or blocked capabilities.
4. Implement one P0 journey across launch, navigation, data, offline or background, permission, error, upgrade, and recovery paths.
5. Run source and target builds plus unit, integration, UI, accessibility, performance, network, offline, process-death, link, push, permission, and upgrade tests on declared devices.
6. Produce signing, privacy, store, staged-rollout, crash, rollback, maintenance, and support evidence.

## Required repository outputs

- Mobile runtime and device fingerprint plus exact target profiles
- Mobile UI and platform-contract IR with source traces
- Generated shared and platform-specific target code, adapters, tests, build, signing, and protected extensions
- Device, lifecycle, offline, accessibility, privacy, performance, rollout, and representative journey evidence

## Verification

- Build and run exact source and target apps on supported OS and device profiles.
- Test cold and warm start, background, foreground, process death, upgrade, deep link, push, offline, sync conflict, permission denial, and secure storage.
- Run accessibility, localization, battery, network, startup, memory, crash, and UI automation checks.
- Verify signing identities, entitlements, privacy manifests, store metadata, staged rollout, and rollback.

## Stop and escalate when

- P0 device, background, push, biometric, lifecycle, or offline behavior is unsupported or undocumented.
- The target requires insecure storage, overbroad permissions, or weaker privacy controls.
- Real-device or representative-emulator evidence is unavailable for certification.
- Store, signing, upgrade, data migration, crash response, or rollback ownership is undefined.

## Definition of done

A real P0 mobile journey runs on the declared device matrix with preserved navigation, lifecycle, offline, permission, storage, deep-link, push, accessibility, privacy, performance, upgrade, and business behavior backed by holdout and release evidence.
