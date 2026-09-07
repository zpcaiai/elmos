---
name: exception-filter-and-error-response-migrator
description: "Migrate framework exception handlers, filters, middleware, Problem Details, status codes, and error response schemas. Use when converting HTTP error boundaries."
---
# Exception Filter and Error Response Migrator
Read `../references/afsm-v1.md`. Preserve handler specificity and scope, cause chains, async rejection, logging ownership, response-started behavior, status, error code and schema.

Keep validation, domain and system errors distinct. Do not swallow catch-all errors, duplicate logs or expose stack traces. Emit partial-response obligations when a standard error response cannot be written after streaming begins.

