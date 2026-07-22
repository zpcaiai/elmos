---
name: oscal-assessment-evidence-and-audit-package-builder
description: Build OSCAL-compatible catalogs, profiles, component definitions, SSPs, assessment plans, results, POA&M, and signed evidence manifests. Use for redacted, offline-verifiable assessment packages.
---

# OSCAL Assessment Package

1. Build Catalog, Profile, Component Definition, System Security Plan, Assessment Plan, Assessment Results, and POA&M as distinct versioned artifacts.
2. Record system boundary, environment, data, users, interconnections, implementations, responsibilities, parameters, objectives, methods, subjects, sampling, assessor, and evidence.
3. Preserve `SATISFIED`, `OTHER_THAN_SATISFIED`, `NOT_APPLICABLE`, `NOT_ASSESSED`, and `INCONCLUSIVE`; never map inconclusive evidence to satisfied.
4. Structure every POA&M item with finding, risk, owner, milestones, due date, resources, status, acceptance, and evidence.
5. Reference source through hashes, summaries, redacted artifacts, and signed reports; exclude raw secrets and unnecessary source.
6. Validate schemas, references, hashes, signatures, required artifacts, control coverage, and evidence freshness offline.

## Acceptance

Do not sign or deliver a package with broken references, stale evidence, missing required objects, or leaked secrets.
