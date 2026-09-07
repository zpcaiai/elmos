---
name: b30-jakarta-ee-modernization
description: Modernize Java EE or Jakarta EE applications from application-server runtimes into a certified target profile, preserving Servlet/JAX-RS, CDI/EJB, JPA, JTA, JMS, security, naming, packaging, lifecycle, and operational behavior.
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


## Skill 1167: Jakarta EE and Java EE modernization

Extract repository and application-server behavior into framework contracts and migrate a deployable EAR/WAR or modular enterprise application to an approved modern target.

## Use this skill when

- A repository depends on Java EE/Jakarta EE APIs, EAR/WAR packaging, or application-server services.
- A customer wants to leave a legacy application server or modernize to Spring, Quarkus, Micronaut, or another target.
- Current migration misses JNDI, EJB, JTA, JMS, realms, classloading, or server configuration.

## Framework-specific risks and invariants

- Behavior can live in descriptors, deployment plans, JNDI resources, realms, clusters, shared libraries, and server administration outside source control.
- EJB pooling, local/remote interfaces, transactions, concurrency, timers, and security may not map directly.
- JTA/XA and JMS delivery guarantees can be silently weakened by an unsuitable target.
- EAR classloading and proprietary server extensions create hidden dependencies.

## Workflow

1. Inventory EAR/WAR/JAR modules, descriptors, server configuration exports, JNDI resources, realms, datasources, queues/topics, clustering, shared libraries, and proprietary extensions.
2. Build/deploy the source on the exact supported server and fingerprint active Servlet/JAX-RS, CDI/EJB, JPA, JTA, JMS, validation, security, timers, naming, lifecycle, and management behavior.
3. Extract FCM plus server-resource, packaging, remote-contract, and classloader contracts; mark missing external evidence as blockers.
4. Select an exact target profile and decide per capability: direct mapping, native rewrite, adapter, retained service, sidecar, coexistence, or block.
5. Implement one complete enterprise vertical slice including module restructuring, DI, transaction, persistence, messaging, security, configuration, and operations.
6. Run source and target runtime contract/behavior tests including transaction, failure, restart, timer, and message cases.
7. Run holdout cases for proprietary features, remote interfaces, classloaders, timers, XA, and custom server integrations.
8. Produce coexistence, server-decommission, external-resource, rollback, and certification evidence.

## Required repository outputs

- `framework-packs/jakarta-ee-to-<target>/`
- Application-server resource/deployment and classloader manifest
- JNDI/JTA/JMS/security/remote-contract mappings
- Target adapters, recipes, and retained-service plan
- Coexistence and server-retirement checklist
- Real source/target runtime evidence

## Verification

- Build and deploy the source to the exact server profile.
- Build/start the target and execute JAX-RS/Servlet, CDI/EJB, JPA, JTA, JMS, security, timer, lifecycle, and remote tests.
- Verify rollback/coexistence for non-atomic transitions.
- Run holdout and representative enterprise applications.

## Stop and escalate when

- Required server configuration or external resource definitions are unavailable.
- JTA/XA, security realm, or remote contracts would be downgraded silently.
- Active proprietary extensions are neither retained, adapted, nor blocked.
- The migration has no viable coexistence or rollback path.

## Definition of done

The pack captures repository and server-side behavior, migrates a real enterprise slice, passes transaction/security/message/runtime and holdout tests, and provides explicit coexistence and server-retirement evidence.
