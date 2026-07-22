---
name: python-environment-lock-and-reproduction
description: Capture and reproduce Python interpreter, ABI, platform, dependency, wheel, sdist, native library, CPU/GPU, and lock-file state with uv, pip, Poetry, or Conda adapters. Use for environment snapshots, dependency locking, offline reproduction, wheel matrices, or Python supply-chain analysis.
---

# Python Environment Lock and Reproduction

## Reproduce before upgrading

Execute stages in order: capture existing environment, reproduce without change, normalize metadata, generate a candidate lock, prove offline reproduction, then create the target lock. Do not upgrade dependencies before the original environment is reproduced or explicitly declared unreproducible.

Capture implementation/version, ABI, OS/architecture, glibc or musl, package manager, distributions and hashes, wheel tags, native libraries, locale/timezone, CPU features, and the GPU stack. Record environment variable keys only; obtain values through approved secret leases when execution requires them.

## Preserve package-manager choice

Prefer an existing valid lock. Support `uv.lock`, `pylock.toml`, Poetry, Pipenv, Conda lock, and hash-pinned requirements. Use uv as the default modern adapter, not as mandatory customer policy. Keep pip, Poetry, and Conda adapters.

Resolve per Python/platform/architecture/extra/GPU marker. Record every wheel or sdist URL, hash, build backend, and build requirement. Build sdists only in a network-denied, secret-free sandbox with fixed inputs, logs, and SBOM.

## Classify evidence honestly

Return one of `BITWISE_REPRODUCIBLE`, `DEPENDENCY_REPRODUCIBLE`, `FUNCTIONALLY_REPRODUCIBLE`, `PARTIALLY_REPRODUCIBLE`, or `UNREPRODUCIBLE`, including the applied definition. Treat unpinned sources, unknown Git branches, unresolved native libraries, missing hashes, and incompatible wheel tags as blockers or explicit gaps.

Accept only when locks are bound to interpreter/platform, artifacts are hashed, ABI/native dependencies are visible, offline installation is exercised, and adapter choice remains replaceable.

