---
name: b32-form-binding-validation
description: Migrate form models binding validation timing conditional fields accessibility submission error focus file inputs draft persistence and server error reconciliation through explicit contracts.
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

## Skill 1210: Form binding and validation migration

## Use this skill when

- A user journey contains forms, wizard steps, server validation, file uploads, drafts, or conditional fields.
- Target forms compile but differ in requiredness, validation timing, errors, submission, focus, or accessibility.
- Legacy behavior is spread across templates, client scripts, server binders, and API validation.

## Client-specific risks and invariants

- Missing, empty, null, default, unchanged, and invalid are distinct states.
- Validation can run on input, blur, step change, submit, or server response and can depend on locale, permissions, and other fields.
- Error summaries, focus, labels, descriptions, live regions, keyboard order, CSRF, and duplicate-submit protection are part of the contract.

## Workflow

1. Inventory fields, nested models, binding names, defaults, visibility, validation rules, server errors, drafts, file inputs, submit behavior, and accessibility relationships.
2. Emit typed form, field, binding, validation, dependency, step, submission, and error contracts with source traces.
3. Map source and API validation into a target form strategy while keeping client and server authority explicit.
4. Generate target form components, schemas or validators, upload handling, draft persistence, error reconciliation, and protected extension points.
5. Run keyboard, assistive-technology, locale, validation-timing, conditional-field, double-submit, timeout, retry, and server-error scenarios.
6. Compare submitted payloads, network calls, errors, focus, audit, and business side effects rather than visible messages only.

## Required repository outputs

- Form, field, binding, validation, submission, and error nodes in UI IR
- `transformations/forms/` mappings and generated target forms
- Client and server validation authority, CSRF, duplicate-submit, upload, and error-contract manifests
- Form interaction, accessibility, payload, network, and business evidence

## Verification

- Run valid, invalid, missing, empty, null, boundary, locale, server-error, retry, and duplicate-submit cases.
- Verify payload shape, timing, message code, error focus, label association, live regions, file limits, and draft recovery.
- Confirm unavailable or unauthorized fields cannot be submitted and server remains authoritative.
- Compare business state after successful and failed submissions.

## Stop and escalate when

- Binding or validation authority is unknown for a P0 field.
- The target needs weaker validation, upload controls, CSRF, authorization, or duplicate-submit protection to pass.
- Accessibility relationships, keyboard behavior, or server-error mapping cannot be preserved or explicitly remediated.
- Test data would contain unapproved personal, health, payment, credential, or customer information.

## Definition of done

P0 forms have explicit binding and validation contracts, and target implementations preserve payloads, timing, errors, focus, accessibility, security, draft, upload, and business side effects across representative journeys.
