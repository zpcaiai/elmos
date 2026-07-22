---
name: b30-flask-migration
description: "Implement or certify a Flask source or target framework pack, including app factories, blueprints, route ordering, request/application contexts, decorators, middleware/hooks, configuration, sessions, extensions, templating, error handlers, WSGI lifecycle, and provider integrations."
---

## Operating mode

Work in the repository. Inspect existing Batch 20-29 modules, contracts, build commands, framework packs, and tests before editing. Implement the smallest production-shaped vertical slice that satisfies this skill; do not stop at a design document when code, manifests, and executable tests can be added.

Read these shared contracts first:

- `../../../docs/batch30/IMPLEMENTATION_CONTRACT.md`
- `../../../docs/batch30/QUALITY_GATES.md`
- `../../../docs/batch30/REPOSITORY_LAYOUT.md`
- `../../../docs/batch30/VERSION_POLICY.md`

Use the supplied helpers where applicable:

- `python3 scripts/batch30/scaffold_framework_pack.py ...`
- `python3 scripts/batch30/validate_framework_pack.py ...`
- `python3 scripts/batch30/run_framework_gate.py ...`

## Global constraints

- Treat every framework migration pack as directional and version-specific. Reverse migration and version upgrade are separate packs.
- Extract runtime behavior into the framework-neutral Framework Contract Model before generating target code. Do not implement annotation-name substitution as the migration architecture.
- Invoke real source and target build/runtime tools. A generated project that only parses is not evidence of support.
- Preserve authentication, authorization, transaction, persistence, message delivery, configuration precedence, validation, lifecycle, and error contracts.
- Keep development, holdout, and representative-repository corpora physically separate. Do not author rules from holdout cases.
- Prefer deterministic mappings and certified adapters. Model-generated output is a candidate and must pass the same build, contract, behavior, security, and test-integrity gates.
- Record unsupported, conditional, and unknown behavior explicitly. Never hide it with TODOs, permissive stubs, broad exception swallowing, disabled security, or weakened tests.
- Record exact framework/runtime/provider versions, source and target commits, recipe digest, model/prompt versions, toolchain digests, and evidence references.
- Fix repeated failures in the fingerprint, contract model, recipe, adapter, or generator instead of patching many generated files.
- Run the narrowest relevant tests first, then the independent holdout suite and framework certification gate before making release claims.


## Skill 1174: Flask framework migration

Migrate Flask applications without losing dynamic registration, context-local, extension, route, error, session, configuration, template, and WSGI lifecycle behavior.

## Use this skill when

- Flask is the source or target.
- A Flask application is moving to FastAPI, Django, Spring, ASP.NET, NestJS, or another framework.
- A current Flask pack lacks runtime route/extension discovery.

## Framework-specific risks and invariants

- App factories, blueprints, decorators, extension initialization, and dynamic imports make static discovery incomplete.
- Request/application contexts and teardown callbacks have precise lifecycle and cleanup semantics.
- SQLAlchemy, session, auth, migration, cache, CSRF, and CLI extensions are provider-specific.
- Route order, converters, error handlers, templates, and globals affect runtime behavior.

## Workflow

1. Lock Python, Flask, WSGI server, extensions, persistence, session, cache, security, templates, and tests.
2. Fingerprint app factory execution, blueprints, ordered routes/converters, hooks, contexts, errors, config, sessions, templates, CLI, and extensions.
3. Extract FCM and explicit context-lifecycle/extension facts.
4. Select a target profile and implement route, dependency, context, error, session, config, and provider mappings for a complete slice.
5. Generate explicit adapters for context-local or extension behavior that cannot map directly.
6. Run real Flask source and target startup, route order, context cleanup, error, session, security, template/API, persistence, and shutdown tests.
7. Run holdout cases for dynamic blueprint registration, custom converters, nested contexts, teardown failures, and extension order.
8. Publish restricted dynamic patterns and replacement/coexistence guidance.

## Required repository outputs

- `framework-packs/flask-to-<target>/` or reverse pack
- Runtime route/blueprint/extension fingerprint
- Context lifecycle/session/error contracts
- Target mappings/adapters and tests
- Dynamic behavior obligations
- Holdout/certification evidence

## Verification

- Run the real app factory and route-map discovery.
- Run context, teardown, error, session, security, persistence, and provider tests.
- Start target runtime and compare P0 contracts.
- Run holdout and the gate.

## Stop and escalate when

- Dynamic registrations cannot be discovered and are assumed absent.
- Context-local state would leak or be flattened incorrectly.
- Extension order or teardown semantics are ignored.
- Session/security behavior is weakened.

## Definition of done

The Flask pack discovers runtime registrations/extensions, preserves context/session/error behavior for a real slice, passes source-target and holdout tests, and blocks undiscovered dynamic patterns.
