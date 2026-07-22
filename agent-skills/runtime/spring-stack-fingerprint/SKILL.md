---
name: spring-stack-fingerprint
description: Fingerprint Spring Boot, Framework, Cloud, Security, Data, Batch and integration stacks for ELMOS health checks. Use for Spring version detection and modernization compatibility evidence.
---
# Spring Stack Fingerprint

## Workflow
1. Read parent, BOM, managed and direct dependency versions with provenance.
2. Detect configuration and source annotations only as supporting signals.
3. Report conflicting or unresolved versions per module.
4. Separate detected source versions from recommended target lines.

## Acceptance
- Missing Boot/Cloud versions are `INCONCLUSIVE`, not latest-version guesses.
- Fingerprints retain module path and descriptor digest.
- Exact target versions require a versioned compatibility matrix.

