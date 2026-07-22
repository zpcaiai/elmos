---
name: b36-visual-studio-vscode-extensions
description: "Implement and certify Visual Studio and VS Code extensions with shared protocol contracts but host-specific project system workspace trust editing testing review and distribution behavior."
---

# Skill 1290: b36-visual-studio-vscode-extensions

## Use this skill when

- C# and polyglot developers need migration workflows in Visual Studio and VS Code.
- A shared feature set must be delivered without pretending the two hosts have identical APIs or security models.

## Domain-specific risks and invariants

- VSIX and VS Code extension hosts differ in project systems, workspace trust, process isolation, command execution, and update channels.
- A shared codebase can accidentally use the least secure common denominator.

## Workflow

1. Define separate exact host/version matrices for Visual Studio and VS Code plus shared protocol bindings.
2. Implement Visual Studio project-system, editor, command, diff, test, and extension-lifecycle integrations.
3. Implement VS Code workspace-trust, virtual workspace, web/desktop host, command, tree view, webview, diff, testing, and extension-lifecycle integrations.
4. Enforce per-host permissions, path scopes, workspace trust, local-agent launch, and repository write policies.
5. Build, sign, package, install, update, rollback, and uninstall both extension variants in real host harnesses.

## Required repository outputs

- Visual Studio VSIX project and manifest
- VS Code extension project and manifest
- Shared protocol client package and host-specific adapters
- Host-specific compatibility, privacy, performance, and workflow evidence

## Verification

- Run real Visual Studio and VS Code integration or approved extension-host tests.
- Test untrusted workspace behavior, virtual/remote workspaces, stale documents, undo/redo, cancellation, and extension reload.
- Verify signing, package integrity, version compatibility, and update rollback.
- Inspect telemetry and local-agent invocation for source, secret, and path leakage.

## Stop and escalate when

- One host requires bypassing workspace trust or repository policy.
- Host-specific limitations are hidden behind a false shared certification.
- Edits cannot be applied through safe host APIs with undo and freshness checks.
- Real host evidence is absent for a claimed certified host.

## Definition of done

- Each host has an independent support status and evidence set.
- P0 workflows pass in real supported hosts.
- No extension broadens workspace, shell, network, or repository permissions.
- Shared protocol behavior remains compatible while host-specific differences are explicit.
