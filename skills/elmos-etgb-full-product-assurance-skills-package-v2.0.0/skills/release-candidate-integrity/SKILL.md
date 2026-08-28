---
name: release-candidate-integrity
description: Freeze every model, Prompt, Skill, rule, source, toolchain, Oracle and normalization component into one immutable candidate digest used throughout ETGB.
---

# Release Candidate Integrity

## Candidate contents

A release candidate includes source commit, model/provider and immutable revision, Prompt digest, Skill manifest digest, rule/recipe bundle digest, toolchain and image digest, dependency policy, Oracle version, normalization version, cache policy and optional feature flags.

## Freeze workflow

1. Reject branch names, `latest`, `stable`, floating model aliases and unpinned images.
2. Validate Git SHA and SHA-256 component digests.
3. Canonicalize the candidate document.
4. Compute and persist `candidate_digest`.
5. Bind run plans, checkpoints, evidence, caches, billing and release decisions to that digest.
6. Treat any component change as a new candidate, even when marketing version is unchanged.

## Runtime checks

At each shard and resume, verify candidate digest, toolchain image, Skill/rule bundle, Oracle and normalization versions. Do not merge results from different candidates into one score. Cache reuse requires an exact candidate-semantic key.

## Drift handling

Provider-side model drift, revoked image, dependency resolution drift or policy refresh blocks the run or creates a new candidate. Never relabel old evidence as if it came from the new candidate.

## Implementation

Use `etgb/candidate.py`, `schemas/release-candidate.schema.json` and `etgb freeze-candidate`.

## Hard gate

Mutable or mixed candidate evidence invalidates release certification, regardless of behavioral score.
