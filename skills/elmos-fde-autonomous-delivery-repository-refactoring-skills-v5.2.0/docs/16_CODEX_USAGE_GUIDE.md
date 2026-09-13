# 16 — Codex Usage Guide

## Recommended first prompt

```text
Use elmos-fde-package-navigator. Inspect the target Elmos repository and this package. Resolve all symbolic routeOwnerRef values against the existing K1-K8/Domain Pack registry. Produce a gap report and an executable B00-B05 plan in PLANS.md. Do not create duplicate owners, do not edit production integration code yet, and run package validation.
```

## Implement one Skill

```text
Use elmos-fde-implement-component-skill for <skill-id>. Implement one thin vertical slice from schema through persistence, workflow, Adapter, API/UI projection, tests and evidence. Keep the write scope explicit; update PLANS.md after checkpoints; do not self-approve.
```

## Assess a repository

```text
Use elmos-fde-audit-existing-repository in read-only mode. Freeze the RevisionSet, build a support profile, report Observed/Verified-Absent/Unknown/Unsupported coverage, normalize findings and produce no source edits.
```

## Execute a refactor

```text
Use elmos-fde-execute-refactor for the approved plan step. Work in an isolated workspace, prefer deterministic transformations, intercept unexpected deltas, produce one reversible ChangeSet, then hand it to elmos-fde-verify-change.
```

## Parallelism

Use read-heavy Subagents for repository exploration, audits and evidence comparison. Keep write-heavy work isolated by plan step/worktree. Never let parallel workers share mutable authority or commit to the same workspace without fencing.
