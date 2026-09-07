---
name: b30-django-migration
description: "Implement or certify a Django source or target migration pack covering settings, apps, URL routing, middleware, ORM, migrations, authentication/permissions, forms, templates, signals, admin, caching, management commands, tasks, and Django REST Framework when present."
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


## Skill 1173: Django framework migration

Extract and migrate exact-version Django behavior while preserving URLs, middleware, settings, ORM, schema migrations, auth, forms/templates, signals, admin, tasks, and operations.

## Use this skill when

- Django or Django REST Framework is a source or target.
- A Django monolith is being decomposed or moved to another stack.
- A Django upgrade needs deterministic recipes and real migration evidence.

## Framework-specific risks and invariants

- Behavior is distributed across settings, apps, URLs, middleware, models, migrations, signals, commands, templates, and admin.
- QuerySets/managers, lazy evaluation, transactions, constraints, migrations, and database backends require execution evidence.
- Auth backends, permissions, sessions, CSRF, middleware order, and DRF policies are security contracts.
- Signals and overridden model/admin/form hooks can create hidden side effects.

## Workflow

1. Lock Python, Django, DRF, database, cache, task, template, ASGI/WSGI, and test versions.
2. Fingerprint settings precedence, installed apps, URLs, middleware, views/viewsets, serializers/forms, auth/permissions, models/managers/querysets, migrations, signals, admin, commands, cache, and tasks.
3. Extract FCM plus Django model/migration/template/admin extensions.
4. Select a target profile and classify admin, templates, signals, commands, and generic framework features as migrate, retain, replace, adapter, or block.
5. Implement a complete protected web-to-data slice and schema/data migration behavior.
6. Run source/target build/startup plus route, middleware, CSRF/session/auth, validation, ORM/query, transaction, migration, signal, error, and shutdown tests.
7. Run holdout cases for custom managers, inheritance, generic relations, signals, DRF policies, templates, admin, and custom commands.
8. Publish data/schema, admin replacement, operational, coexistence, and certification guidance.

## Required repository outputs

- `framework-packs/django-to-<target>/` or exact upgrade pack
- Settings/app/URL/middleware/runtime fingerprint
- ORM/migration/auth/DRF/template/admin contracts
- Target recipes and retained/replacement plan
- Database migration and behavior evidence
- Holdout/certification artifacts

## Verification

- Run Django system checks, migration plan/check, tests, and source startup.
- Run target build/startup and web/security/data/transaction/error tests.
- Compare schema, migration, and representative query behavior.
- Run holdout and the framework gate.

## Stop and escalate when

- Django migrations or live schema evidence is unavailable.
- Signals, auth, permissions, or middleware are silently omitted.
- ORM behavior is inferred without real queries.
- Admin/template functionality is claimed migrated without an explicit target experience.

## Definition of done

The Django pack captures active project/runtime behavior, migrates a real slice and schema, passes web/security/ORM/transaction/holdout tests, and explicitly handles admin, template, signal, and task boundaries.
