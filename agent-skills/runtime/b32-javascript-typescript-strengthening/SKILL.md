---
name: b32-javascript-typescript-strengthening
description: "Strengthen JavaScript into TypeScript with runtime-shape discovery typed boundaries null and undefined semantics module and async analysis generated declarations strictness rollout and behavior-preserving validation."
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

## Skill 1218: JavaScript to TypeScript strengthening

## Use this skill when

- A client or Node codebase needs JavaScript-to-TypeScript modernization.
- Existing migration compiles only because of broad any use, disabled strictness, or suppressions.
- Typed contracts are needed before framework migration, SDK generation, or client hardening.

## Client-specific risks and invariants

- Static inference cannot safely recover dynamic property mutation, prototypes, monkey patches, mixed modules, runtime validation, or external data shapes.
- Null, undefined, missing properties, truthiness, narrowing, serialization, and optionality require explicit treatment.
- Using any, unsafe assertions, ignore directives, or disabled strictness hides migration risk.

## Workflow

1. Fingerprint JavaScript versions, modules, transpilers, build, tests, runtimes, globals, dynamic imports, prototypes, decorators, JSDoc, validation libraries, and external boundaries.
2. Collect static and runtime shape evidence for public functions, components, props, state, events, API payloads, storage, messages, globals, and configuration.
3. Create a typed-boundary and strictness rollout plan prioritizing public contracts, state, forms, API clients, identity, and security-sensitive code.
4. Generate TypeScript, declarations, schemas or runtime validators, discriminated unions, null or undefined contracts, and safe adapters.
5. Eliminate or budget dynamic escape hatches and require owner and evidence for remaining any, suppressions, or unsafe assertions.
6. Run real build, tests, behavior journeys, type coverage, declarations, modules, bundles, runtime validation, and holdout cases.

## Required repository outputs

- JavaScript runtime and dynamic-behavior fingerprint
- Typed boundary, strictness, and escape-hatch migration plans
- TypeScript code, declarations, runtime validators, adapters, and protected ownership
- Build, behavior, bundle, type-coverage, runtime-shape, and holdout evidence

## Verification

- Run exact source and target builds and application journeys.
- Enable the declared strictness profile and enforce no new unapproved any, ignore directives, or unsafe double assertions.
- Verify null, undefined, missing, truthiness, modules, async, events, and serialization boundaries.
- Run holdout cases for dynamic properties, mixed modules, external JSON, and runtime validation failure.

## Stop and escalate when

- The strategy is broad any, disabled strictness, or mass suppression.
- Dynamic prototype, monkey patch, global, external-boundary, or reflective behavior remains unknown for a P0 journey.
- Types are generated from assumptions without runtime or contract evidence.
- Behavior, bundle, or test regressions are ignored because the type checker passes.

## Definition of done

P0 public and stateful boundaries are strongly typed and runtime-validated where required, declared strictness passes, escape hatches are bounded and owned, and real journeys plus holdout cases show no critical behavioral regression.
