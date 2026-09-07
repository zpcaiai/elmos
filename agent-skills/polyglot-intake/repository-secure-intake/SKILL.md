---
name: repository-secure-intake
description: Securely accept a Git repository or uploaded tree and bind an immutable, credential-free ELMOS snapshot to exact provenance. Use before any repository analysis or translation.
---

# Repository Secure Intake

Create the only source identity later migration stages may consume.

## Inputs

Require `sourceType`. For Git require a sanitized `repositoryRemote` and full resolved `commitSha`; `branch` is descriptive only. For uploads require a stable `uploadId`. Apply explicit file-count, total-byte, and per-file limits.

## Workflow

1. Validate `https` or `ssh` provenance and reject remotes containing credentials.
2. Resolve a floating ref outside this skill, then pass the full commit SHA.
3. Scan without following links; reject escaping links and special files.
4. Hash every accepted file in stable path order without returning contents.
5. Mark secret-like, binary, generated, and vendored files as excluded from model context.
6. Record `.gitmodules` paths without initializing unknown submodules.
7. Derive `snapshotId` from source identity plus the canonical file manifest.
8. Remove the credential lease before making the snapshot available.

## Hard boundaries

- Never run repository scripts, Git hooks, package lifecycle hooks, or build tools.
- Never use host SSH keys or place tokens in a clone URL, manifest, log, or prompt.
- A branch or tag alone is not immutable provenance.
- Later patches and baseline evidence must use the same `snapshotId`.

## Acceptance

Repeated intake of the same source identity and bytes yields the same snapshot/integrity hash. Credential-bearing remotes, unresolved Git refs, symlinks, special files, and size-limit violations fail closed.
