---
name: b32-ui-interaction-ir
description: "Implement or extend a typed UI Interaction IR for routes views components state events effects forms bindings permissions resources design tokens accessibility and source mapping before client transformation."
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

## Skill 1204: UI component state and interaction IR

## Use this skill when

- A migration lacks a framework-neutral representation of client behavior.
- Target generators read source templates, decorators, JSX, view files, or desktop widget definitions directly.
- State, effects, forms, permissions, focus, lifecycle, or accessibility semantics are stored as opaque metadata or silently lost.

## Client-specific risks and invariants

- A DOM-like tree does not represent ownership, state transitions, effect timing, cleanup, focus, validation, permissions, or navigation.
- Framework lifecycle hooks must be normalized without erasing ordering, async cancellation, subscription, hydration, or disposal semantics.
- Design tokens, content, semantic roles, interaction contracts, native boundaries, and source traces require stable identities.

## Workflow

1. Inspect existing PSP, UIR, Framework Contract, source-map, event, artifact, and evidence schemas and reuse stable identity and provenance conventions.
2. Define versioned nodes for routes, views, components, slots, state variables, derived state, actions, events, effects, forms, resources, permissions, tokens, accessibility, and native boundaries.
3. Implement source adapters that emit UI IR rather than target code and retain exact source ranges, runtime evidence, confidence, and unsupported constructs.
4. Model lifecycle and effect ordering, cleanup obligations, async cancellation, data ownership, rendering mode, hydration boundary, browser or native APIs, and accessibility relationships.
5. Add validators for unique IDs, references, source maps, state transitions, effects, form bindings, permissions, route targets, and critical unknowns.
6. Implement serializers, schema migration, generated bindings, fixtures, negative cases, and deterministic round-trip tests.
7. Run one real journey through source adapter, UI IR, target generator, build, runtime, and evidence capture.

## Required repository outputs

- `schemas/batch32/ui-interaction-ir.schema.json` and generated bindings
- `client-packs/<pack>/ui-ir/model.json` plus optional domain fragments
- IR validators, source-map indexes, schema migration tools, and development or negative fixtures
- Node semantics, invariants, extension, unknown, and compatibility documentation

## Verification

- Run JSON Schema validation and repository-native contract tests.
- Validate unique IDs, references, component ownership, route targets, state and action links, cleanup, form binding, permissions, source traces, and accessibility links.
- Compare incremental and full IR generation for the same source snapshot.
- Generate and run one target journey exclusively from UI IR and target profile.

## Stop and escalate when

- The proposed IR is a renamed framework AST or stores core behavior in free-form blobs.
- Critical state, effect, permission, validation, focus, native, or hydration behavior cannot be represented or explicitly marked unsupported.
- Source mapping is absent for P0 routes, components, forms, actions, effects, or permissions.
- A schema change cannot preserve existing certified packs or provide a migration path.

## Definition of done

The UI Interaction IR is typed, versioned, source-traceable, framework-neutral at its core, validated by executable fixtures, capable of representing a complete P0 journey, and consumed by target generation without source-framework coupling.
