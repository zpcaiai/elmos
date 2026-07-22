# ADR-0022: Skeleton-first target generation

- Status: Accepted
- Date: 2026-07-21

## Decision

Batch 4 establishes the target world before translating bodies: one resolved target profile, evidenced stack decisions, module/migration-mode mapping, naming/build graph, repository layout, type/API/async/error/resource signatures, pending tests, configuration/resource placeholders and complete source-to-target mappings.

`modules/skeleton` plans and emits deterministic contract-only repositories for Java, Python, C#, and TypeScript/JavaScript. Placeholder bodies throw or remain abstract; pending tests cannot report success. Generation is idempotent and refuses to overwrite differing manual files. Secrets, vendor trees and unknown binaries are never copied.

Build-model load, dependency resolution, syntax compile and test discovery evidence comes from an approved isolated runner. `NOT_RUN` remains blocked. Skeleton existence or compilation never means implementation or behavioral equivalence.
