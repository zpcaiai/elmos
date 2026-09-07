---
name: compatibility-matrix-resolver
description: Resolve source-to-target compatibility using a versioned ELMOS matrix. Use for JDK, Spring Boot, Jakarta, Security, Hibernate, plugins, drivers or infrastructure compatibility.
---
# Compatibility Matrix Resolver

## Workflow
1. Require source fingerprint, target profile and matrix version.
2. Emit one decision per component with source, target, migration requirement and rationale.
3. Preserve missing entries as `INCONCLUSIVE`.
4. Never mutate a historical plan when the matrix changes; create a new revision.

## Acceptance
- Every decision records matrix version.
- Missing source or target versions block affected steps.
- Compatibility is not inferred from successful compilation alone.

