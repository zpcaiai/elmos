---
name: identity-security-integration-tests-and-release-gates
description: "Add real PostgreSQL, OIDC, tenant-isolation, authorization, frontend, and startup-security tests that act as mandatory release gates."
---

# Objective

Turn identity and tenant security from configuration claims into executable
release gates.

A passing unit test suite alone is insufficient.

The test matrix must validate:

- identity verification;
- tenant resolution;
- membership lifecycle;
- resource authorization;
- PostgreSQL RLS;
- connection-pool isolation;
- frontend BFF behavior;
- startup readiness.

# Test layers

## Layer 1: domain unit tests

Cover:

- membership state transitions;
- tenant selection rules;
- permission evaluation;
- SoD decisions;
- expiration;
- resource grant matching.

## Layer 2: Spring security integration tests

Cover:

- unauthenticated requests;
- JWT issuer;
- JWT audience;
- expired token;
- tenant candidate;
- endpoint method security;
- application service authorization.

## Layer 3: real PostgreSQL RLS tests

Use Testcontainers or a repository-supported PostgreSQL test environment.

Tests must execute SQL as:

```text
elmos_runtime
