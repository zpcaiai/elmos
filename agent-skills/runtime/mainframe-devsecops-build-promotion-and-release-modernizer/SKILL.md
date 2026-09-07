---
name: mainframe-devsecops-build-promotion-and-release-modernizer
description: Integrate mainframe source, copybooks, compiler/precompiler/binder configuration, JCL, tests, load modules, SCM, promotion, runtime verification, RACF/SAF, and audit into governed CI/CD. Use for Git or traditional SCM coexistence, z/OS builds, loadlib promotion, and release traceability.
---

# Mainframe DevSecOps

## Build traceably

1. Bind source commit or SCM package, dataset mapping, copylib versions/search order, compiler and options, precompiler, binder, JCL, target loadlib, environment, and promotion path.
2. Record compiler version, warnings, listing, binder map, return code, load-module digest, and all input dataset versions.
3. Support Git, Endevor, Changeman, ISPW, and custom SCM through adapters; do not force a big-bang SCM replacement.
4. Promote the same artifact or prove controlled artifact equivalence across development, test, integration, preproduction, and production.
5. Verify the deployed load-module digest and runtime region after promotion.

## Enforce separation of duty

- Use individual SAF identities, scoped datasets, approved job classes, signed evidence, and complete audit.
- Freeze copybooks and build configuration for a release.
- Require an independent approver for production promotion and a verified rollback module.
