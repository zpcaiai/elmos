---
name: migration-path-planner
description: Build the deterministic ELMOS modernization DAG. Use for ordering baseline, JDK, plugins, Spring Boot, Jakarta, Security, Hibernate, tests and API validation.
---
# Migration Path Planner

## Workflow
1. Create stable step IDs and explicit dependency edges.
2. Topologically order baseline, JDK, build, framework, namespace, sensitive subsystem, test and API steps.
3. Attach objective, risk, automation score and required evidence to every step.
4. Reject cycles, missing parents or duplicate step IDs.

## Acceptance
- The plan is a valid DAG.
- Sensitive steps cannot bypass approval gates.
- A step cannot succeed without all required evidence.

