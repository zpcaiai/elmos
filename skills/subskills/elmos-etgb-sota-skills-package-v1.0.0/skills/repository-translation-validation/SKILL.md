---
name: repository-translation-validation
description: Validate whole-repository cross-language conversions with executable semantics, architecture adaptation, dependency handling, and hidden tests.
---

# Repository Translation Validation

## Principle

Repository translation is not concatenated file translation. Correctness includes module topology, public API, protocol, data, transactions, concurrency, resources, build, deployment and tests.

## Workflow

### 1. Build Repository Semantic Graph

Capture modules/packages, symbols, type relationships, call graph, data flow, schemas, routes/RPC, messages, build/dependencies, configuration, resources, tests, native/FFI and deployment.

### 2. Baseline source

Pin runtime and dependencies; build and execute public plus generated characterization tests. Collect outputs, state, trace, resource and error semantics.

### 3. Map semantic gaps

For every source construct classify:

- direct equivalent;
- target idiom with proof obligation;
- compatibility adapter;
- architecture transformation;
- unsupported/manual.

Examples include ownership/GC, channels/tasks, reflection, dynamic typing, multiple inheritance, checked exceptions, decimal, timezone and event loops.

### 4. Translate repository

Preserve behavior while producing a valid target build ecosystem. Do not mechanically reproduce source anti-patterns when a target adaptation can be proven equivalent. Emit adaptation records and confidence/evidence requirements.

### 5. Validate target independently

- clean build and lockfile;
- API/schema/protocol conformance;
- translated original tests;
- independently generated hidden tests;
- differential execution and state comparison;
- concurrency scheduler/invariants;
- memory/resource cleanup;
- security and performance.

### 6. Verify completeness

Compare source semantic graph against target and unsupported manifest. Flag missing public symbols, routes, resources, migrations, configs, tests or side effects. Empty stubs and constant-return implementations fail.

### 7. Statistical evaluation

For Agentic translation run multiple fixed seeds and report success distribution, repair turns, token/credit, wall-clock and worst-case. Do not publish only the best seed.

## Frontend/miniapp

For Vue/React/Flutter → miniapp compare component/state/router/form/network/auth/platform permissions/payment/share/deep-link/UI interaction and package limits. Platform capabilities with no direct equivalent require adapters or disclosure.

## Native

For Objective-C/Swift/Android Kotlin validate ownership, lifecycle, UI-thread, secure storage, permission manifests, background execution, signing disclosures and native dependencies.

## P0 failures

- target builds but hidden behavior differs;
- decimal/timezone/security/concurrency changes;
- missing source capability not disclosed;
- target test suite weakened to pass;
- dependency substituted without contract evidence.
