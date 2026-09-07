---
name: b32-client-estate-discovery
description: "Discover and fingerprint pages components templates routes state stores forms API clients assets design systems browser APIs accessibility tests runtime rendering and device behavior before client modernization."
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

## Skill 1205: Page component asset and runtime discovery

## Use this skill when

- A client application needs assessment, scoping, target selection, or migration planning.
- Static dependency scans do not explain active routes, loaded components, feature flags, network calls, browser storage, or runtime behavior.
- A certification pack lacks a reproducible source fingerprint.

## Client-specific risks and invariants

- Dead templates and declared dependencies can be mistaken for active behavior while dynamic routes, imports, plugins, or server-generated views are missed.
- CSS, fonts, images, localization catalogs, analytics, service workers, browser storage, native bridges, accessibility, and test locators are part of the estate.
- Feature flags, tenant configuration, permissions, A or B tests, and runtime data can alter the active component graph.

## Workflow

1. Collect manifests, lock files, build configuration, source maps, server view configuration, templates, styles, assets, tests, browser declarations, mobile or desktop metadata, and deployment configuration.
2. Build static indexes for routes, views, imports, dynamic imports, state stores, forms, API clients, storage, workers, browser or native APIs, analytics, i18n, and assets.
3. Run the exact source application and capture route discovery, rendered semantic trees, network, state transitions, feature flags, accessibility trees, screenshots, console errors, and performance for representative journeys.
4. Classify capabilities as active, conditional, test-only, dead, generated, external, or unknown and attach source and runtime evidence.
5. Map route and component ownership, shared libraries, design-system dependencies, browser or device constraints, and migration blockers.
6. Write the source fingerprint and evidence summary without copying unapproved sensitive payloads.

## Required repository outputs

- `source-fingerprint/manifest.json` with exact source tuple, snapshot digest, and coverage
- `source-fingerprint/static/` and `source-fingerprint/runtime/` evidence
- Route, component, form, state, API, asset, accessibility, test, browser, and device inventories
- A migration-scope report and unknown-critical capability list

## Verification

- Launch the exact source and replay representative journeys in the declared browser or device matrix.
- Cross-check static findings against runtime navigation, network, state, and rendered trees.
- Verify fingerprint digest, coverage, evidence references, and exact dependencies or tool versions.
- Run negative discovery fixtures for dynamic imports, flags, nested templates, service workers, generated code, and native bridges.

## Stop and escalate when

- The source cannot be built or launched and no approved assessment-only mode exists.
- Only package manifests or screenshots are available with no runtime evidence for certification.
- Production capture would expose credentials, personal, payment, health, or customer data without an approved privacy workflow.
- Dynamic routes, permissions, rendering, or native behavior remains unknown for a P0 journey.

## Definition of done

The source estate has an exact reproducible static and runtime fingerprint with evidence-backed active capabilities, route and component ownership, browser or device constraints, privacy-safe representative journeys, and explicit unknowns.
