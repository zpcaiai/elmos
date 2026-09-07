---
name: static-build-time-security-analysis-orchestrator
description: Orchestrate authorized SAST, SCA, secret, IaC, container, license, configuration, client, and database static analysis. Use when normalized findings and measurable coverage are required.
---

# Static Security Analysis

1. Select replaceable adapters by language, framework, artifact, license, deployment, profile, residency, and offline policy.
2. Scan the declared source, manifests, lockfiles, build artifacts, images, IaC plans, Kubernetes manifests, packages, and database scripts.
3. Normalize category, CWE/CVE, asset, location, confidence, source tool/rule, root cause, and evidence.
4. Deduplicate by asset, symbol, flow, component, vulnerability, artifact, and root cause; never deduplicate only by title.
5. Measure files, modules, languages, rules, dependencies, artifacts, exclusions, parse errors, timeouts, and build coverage.
6. Separate existing, migration-introduced, migration-exposed, resolved, and new-rule findings; time-box every suppression.

## Acceptance

Parse errors and exclusions lower coverage. No findings with insufficient coverage yields `COVERAGE_INSUFFICIENT`, never `PASS`.
