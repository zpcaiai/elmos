---
name: spring-modernization-validation
description: Validate repository-level modernization of Servlet, JSP, Struts, Spring Framework, and Spring Boot legacy systems to Spring Boot 4.
---

# Spring Modernization Validation

## Scope

Servlet/JSP/web.xml, Spring XML MVC, Struts 1, Struts 2, mixed repositories, Boot 1/2/3 → Boot 4, including routes, binding, Session, Filter/Interceptor, validation, exceptions, transactions, security, views, integrations, build and operations.

## Inputs

- immutable source commit and build environment;
- migration target and allowed architecture changes;
- database/external service fixtures;
- critical business workloads;
- known source defects and accepted differences.

## Workflow

### 1. Inventory

Extract build graph, Java/Spring/Servlet/Struts versions, modules, web.xml/struts.xml/XML beans, routes, forms, views, tags, filters, listeners, interceptors, transactions, ORM, DB objects, security rules, messaging and deployment.

### 2. Establish source baseline

Run clean build twice; record tests and flakiness. Start source in sandbox and probe:

- route/method/status/header/content type;
- binding and validation errors;
- Session/Cookie lifecycle;
- Filter/Interceptor order;
- views/DOM/model;
- exception mappings;
- DB/transaction and external side effects;
- allow/deny security matrix;
- health, metrics, logs and shutdown.

Never begin equivalence claims from a broken or unknown baseline.

### 3. Generate contract bundle

Create normalized HTTP scenarios, browser flows, database seeds, message scripts, fault points and state snapshots. Separate stable business fields from explicitly dynamic fields.

### 4. Modernize

Transformation worker has no permission to edit baseline contracts or hidden tests. It must emit:

- transformed repository;
- migration manifest;
- unsupported/manual list;
- dependency/config changes;
- rollback and deployment notes.

### 5. Target build and static checks

Verify clean build, dependency convergence, Java/Jakarta/Spring API, bean graph, routes, schema migrations, security configuration, SBOM and container non-root policy.

### 6. Dual run

Replay identical workload against source and target. Invoke differential Oracle for HTTP, DOM, Session, DB, messages, traces and errors. For transaction cases inject failure after each write and before each commit.

### 7. Negative security

Test anonymous, wrong role, expired/forged token, CSRF missing, CORS disallowed, session fixation, method security and path precedence. A target that is more permissive fails even when happy-path login works.

### 8. Operational validation

Test startup, readiness, graceful shutdown, reverse proxy headers, TLS, external config precedence, memory/thread leaks and performance budgets.

## Claim policy

- P0 equivalence mismatch: fail.
- Unsupported third-party API: explicit adaptation/manual approval, never silent deletion.
- Intentional source-bug fix: requires separate approved behavior-change contract; do not mix with equivalence score.

## Golden Route promotion

A repository enters Golden Route only after repeated clean runs, zero P0 SSER, reproducible environment, approved corpus/license and signed evidence.
