---
name: b36-pr-bot
description: "Implement a least-privilege GitHub GitLab and Bitbucket pull-request bot for migration checks summaries annotations approvals commands and evidence without uncontrolled code changes or comment spam."
---

# Skill 1292: b36-pr-bot

## Use this skill when

- Migration results and incremental updates need to appear in normal code-review workflows.
- Teams need status checks, annotations, commands, and evidence links across supported SCM providers.

## Domain-specific risks and invariants

- A bot can gain broad repository permissions, execute untrusted PR content with secrets, spam comments, or approve its own changes.
- Provider APIs and event semantics differ and must not be falsely treated as identical.

## Workflow

1. Lock exact SCM provider/API/app versions and define per-provider installation, identity, permission, event, and rate-limit profiles.
2. Define webhook verification, replay protection, repository/branch policy, fork handling, command authorization, and idempotent delivery.
3. Implement checks, annotations, one updatable summary, scoped slash commands, review requests, and evidence links.
4. Separate read-only analysis from write operations and require explicit policy or approval for branch updates.
5. Test against real provider sandboxes including forks, renamed branches, force pushes, rate limits, duplicate webhooks, and app uninstall.

## Required repository outputs

- `pr-bot/policy.json`, provider adapters, webhook contracts, permissions manifest
- Provider sandbox evidence, rate-limit and replay tests, comment/update snapshots
- Status-check and annotation mapping to exact commit SHA and migration manifest

## Verification

- Verify webhook signatures and duplicate delivery idempotency.
- Test minimal permissions, fork PR isolation, branch protection, command authorization, comment deduplication, and rate limits.
- Verify checks become stale when commit SHA changes.
- Ensure the bot cannot self-approve high-risk changes or bypass required reviewers.

## Stop and escalate when

- A provider requires broad organization or repository permissions beyond policy.
- Untrusted PR code can access credentials or privileged runners.
- Results cannot bind to exact commit SHA and artifact digests.
- The bot cannot avoid duplicate comments or actions on replay.

## Definition of done

- Each provider has an independent support status.
- P0 PR workflows pass in real provider sandboxes.
- Unapproved repository writes, secret exposure, self-approval, and comment spam are zero.
- Checks and evidence are traceable to exact commits.
