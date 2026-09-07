---
name: openapi-contract-and-route-reconciler
description: "Reconcile source-code routes, reviewed source OpenAPI, AFSM endpoints, and generated target OpenAPI. Use for Batch 7 contract comparison and breaking-change gates."
---
# OpenAPI Contract and Route Reconciler
Read `../references/afsm-v1.md`. Apply an explicit authority policy and compare path, method, operation ID, parameters, required/default/nullability, schema, status, headers, media type, security, errors, versions and deprecation.

Classify code-versus-contract, source-versus-target, missing/extra endpoint and breaking schema/security/serialization conflicts. Never silently choose a side. Require approval for breaking changes and keep runtime differential tests because OpenAPI equality is not behavior proof.

