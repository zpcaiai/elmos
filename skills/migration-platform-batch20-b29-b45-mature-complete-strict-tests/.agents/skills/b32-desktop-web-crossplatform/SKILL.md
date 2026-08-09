---
name: b32-desktop-web-crossplatform
description: Modernize desktop UI and native-bound workflows into web or cross-platform targets with explicit threading command data-binding window file device offline native-integration accessibility and deployment contracts.
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

## Skill 1219: Desktop UI to web or cross-platform migration

## Use this skill when

- A desktop or thick-client application must move to web, cross-platform desktop, or a hybrid shell.
- The source uses WPF, WinForms, Swing, JavaFX, native widgets, local files, devices, COM, or platform integration.
- A pack must separate migratable UI from retained native, device, or offline capabilities.

## Client-specific risks and invariants

- Desktop applications can depend on thread affinity, modal flows, commands, data binding, window lifetime, local files, printers, scanners, serial devices, native APIs, background workers, and offline state.
- Moving to web changes trust, sandbox, filesystem, update, deployment, latency, accessibility, keyboard, and multi-window semantics.
- Some native behavior needs a signed local agent, sidecar, retained runtime, or approved cross-platform shell rather than direct rewriting.

## Workflow

1. Fingerprint exact toolkit, runtime, OS, packaging, update, window, command, binding, threading, storage, device, native, accessibility, and deployment behavior.
2. Extract views, view models, controls, commands, bindings, validation, navigation, dialogs, windows, background tasks, resources, native boundaries, and offline state into UI IR and interop contracts.
3. Classify capabilities for web, cross-platform, hybrid shell, local agent, sidecar, retained runtime, manual redesign, or block.
4. Select an exact target profile and implement one end-to-end workflow with protected extension points and least-privileged native boundaries.
5. Run source and target workflows on declared OS and device profiles including keyboard, accessibility, offline, file, device, update, failure, and recovery.
6. Create deployment, signing, security, support, rollback, maintenance, and retirement evidence.

## Required repository outputs

- Desktop runtime fingerprint, UI IR, and native-boundary inventory
- Target profile and web, cross-platform, hybrid, local-agent, sidecar, retained-runtime, or block decisions
- Generated target workflow, adapters, installers, updates, tests, and protected extensions
- OS, device, accessibility, security, offline, performance, and representative workflow evidence

## Verification

- Run exact source and target applications on supported OS and device configurations.
- Verify command, binding, thread, dialog, window, file, device, offline, update, error, and recovery behavior.
- Perform keyboard, assistive-technology, high-DPI, localization, memory, and performance tests.
- Verify native bridges are signed, least-privileged, auditable, updateable, and restricted to approved scope.

## Stop and escalate when

- P0 behavior depends on undocumented native, device, timing, or thread-affinity semantics.
- A web target is selected despite mandatory offline, device, latency, or security needs without a viable local boundary.
- Native bridge permissions are broad, unsigned, unowned, or unaudited.
- The target removes accessibility, keyboard, file integrity, recovery, or update behavior to simplify implementation.

## Definition of done

A complete desktop workflow is typed, implemented in an exact target strategy, verified on declared OS and devices, and supported by safe native boundaries, deployment, update, offline, accessibility, security, rollback, and retirement evidence.
