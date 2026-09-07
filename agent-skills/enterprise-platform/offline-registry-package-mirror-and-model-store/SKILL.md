---
name: offline-registry-package-mirror-and-model-store
description: Close and verify offline OCI, Maven, NuGet, PyPI, npm, model, SBOM, signature, and vulnerability-feed repositories. Use for Air-gap dependency closure, import, build, test, model load, update, or rollback.
---

# Offline Registry Package Mirror and Model Store

Read `../references/batch-12-enterprise-platform.md`. Resolve all platform, Runner, toolchain, project, transitive package, model runtime/tokenizer and signature artifacts at locked versions; scan, sign, checksum and import with a change manifest.

Offline Runner fallback to public networks, missing transitive content or unscanned imports blocks T-F.
