# Full Project Generator

## Goal

Generate a complete, buildable, testable, deployable, observable, secure, and maintainable repository from an executable specification.

## Required output domains

- domain model and business invariants
- backend services and APIs
- web and/or mobile UI
- database schemas, migrations, and seeds
- identity and authorization
- integrations, queues, jobs, notifications, and files
- tests: unit, contract, integration, end-to-end, property, security, performance
- local development and CI/CD
- containers/infrastructure
- logging, metrics, tracing, dashboards, alerts
- runbooks, architecture decisions, API docs, operations handoff
- evidence and readiness status

## Anti-placeholder policy

Production scope may not contain fake success responses, disabled tests, TODO-only modules, mocked external systems without a declared contract and environment adapter, hard-coded credentials, or generated documentation that claims unexecuted behavior.

## Workflow

Requirements become a requirements graph with acceptance criteria. The generator creates a target profile and architecture decisions, then an executable DAG. Each feature maps to code, tests, and evidence or to an explicit exclusion. The same trusted runner and readiness gates used for migration apply to greenfield generation.
