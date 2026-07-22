---
name: b36-local-migration-preview
description: "Implement a fast deterministic local migration preview and dry-run workflow using pinned artifacts isolated execution explicit diffs no remote writes and reproducible manifests."
---

# Skill 1293: b36-local-migration-preview

## Use this skill when

- Developers need to preview transformations before opening a pull request or starting a remote migration run.
- A local workflow must work with limited connectivity and preserve enterprise data policies.

## Domain-specific risks and invariants

- Local environments drift, tools may execute untrusted code, caches may cross tenants, and previews can differ from certified runners.
- A preview must not silently mutate the repository, remote state, or golden evidence.

## Workflow

1. Define exact preview scope, source commit, target profile, recipe set, toolchain, sandbox, network, model, cache, and output ownership.
2. Implement read-only discovery followed by an isolated temporary workspace and explicit generated diff.
3. Support no-model, local-model, and approved remote-model modes through the same policy layer.
4. Generate a reproducible preview manifest, diagnostics, source maps, affected tests, budget, and cleanup evidence.
5. Compare local output with remote runner output on holdout workflows and explain allowed differences.

## Required repository outputs

- `preview/profile.json`, local preview command/API, sandbox manifest, result manifest
- No-write and cleanup evidence, local/remote equivalence report, cache provenance
- Representative offline/limited-network developer workflow

## Verification

- Run preview twice from a clean checkout and compare artifact digests.
- Verify source repository, remote branches, databases, brokers, and golden baselines remain unchanged.
- Test network deny-by-default, cache isolation, cancellation, disk exhaustion, and cleanup failure.
- Compare local and certified-runner results for the same pinned inputs.

## Stop and escalate when

- Required toolchain or artifact versions cannot be pinned.
- Preview would require production credentials, unrestricted network, or destructive commands.
- Local and remote outputs diverge without an approved explanation.
- Cleanup or source-repository immutability cannot be proven.

## Definition of done

- A developer obtains an accurate diff and evidence without remote writes.
- Preview is reproducible from its manifest and bounded by policy.
- Local/remote parity meets the profile.
- No source, secret, cache, or workspace residue crosses scope.
