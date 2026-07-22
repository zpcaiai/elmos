---
name: source-resource-inventory
description: Inventory production, test, generated, configuration, database, API, schema, resource, CI, container, binary and vendored files without exposing secret contents.
---

# Source Resource Inventory

## Workflow

1. Start from the immutable file manifest and repository ignore/build conventions.
2. Classify every file into the canonical Batch 1 categories.
3. Detect generated markers and build-output roots; default them out of direct translation.
4. Detect vendor/third-party roots; default them out of modification.
5. Identify binaries and retain metadata only.
6. Identify SQL/migrations, OpenAPI/GraphQL/Protobuf/JSON Schema, Docker and CI configuration.
7. Count logical production/test/generated lines and binary bytes.
8. Mark secret-like files `excludedFromModel` and record only safe metadata/digests.

## Hard boundaries

- Never place secret file contents in a model context, artifact preview or log.
- Never translate generated, vendored, or binary content by default.
- Do not infer file purpose from extension alone when path/build evidence conflicts.

## Acceptance

The inventory is complete relative to the snapshot, totals reconcile with file entries, and every excluded file carries a reason visible to later gates.
