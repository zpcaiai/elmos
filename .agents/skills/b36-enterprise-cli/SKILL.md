---
name: b36-enterprise-cli
description: Implement a stable scriptable enterprise CLI for assessment migration preview repair validation evidence runner and pack workflows with deterministic output noninteractive safety and shell-completion support.
---

# Skill 1291: b36-enterprise-cli

## Use this skill when

- Developers, CI systems, and enterprise automation need a supported command-line interface.
- Web-console workflows must be reproducible and composable from scripts without scraping UI output.

## Domain-specific risks and invariants

- Ambiguous defaults, interactive prompts, unstable JSON, unsafe shell interpolation, and hidden context can cause destructive automation.
- CLI credentials and local caches can leak tenant data or source code.

## Workflow

1. Define command hierarchy, nouns, verbs, global flags, config precedence, profiles, authentication, output modes, exit codes, idempotency, and deprecation policy.
2. Implement human-readable, JSON, JSON Lines, and quiet output with versioned schemas.
3. Implement dry-run, explicit confirmation, noninteractive mode, cancellation, resumable operations, timeout, and structured errors.
4. Implement secure credential storage, tenant/project context display, redaction, cache isolation, and shell completion.
5. Add contract tests across supported OS, shells, network modes, and CLI versions.

## Required repository outputs

- `cli/contract.json`, generated command reference, completion scripts, and versioned output schemas
- CLI binary/package manifests, signing/provenance, and installation/update scripts
- Golden command, error, redaction, noninteractive, and representative automation evidence

## Verification

- Run every P0 command against real or approved isolated services.
- Verify stable JSON schemas, exit codes, idempotency, retry, cancellation, and resume behavior.
- Test unsafe argument injection, path traversal, stale context, wrong tenant, missing confirmation, and secret redaction.
- Run supported shell and OS matrix tests.

## Stop and escalate when

- A command can select tenant, project, repository, or environment implicitly in a destructive operation.
- Output schemas or exit codes are not versioned.
- Secrets are stored or printed insecurely.
- Noninteractive execution cannot fail safely.

## Definition of done

- P0 workflows are fully scriptable and deterministic.
- Automation can distinguish success, partial success, retryable failure, policy denial, and user error.
- Security, compatibility, and package provenance evidence pass.
- CLI behavior matches control-plane contracts.
