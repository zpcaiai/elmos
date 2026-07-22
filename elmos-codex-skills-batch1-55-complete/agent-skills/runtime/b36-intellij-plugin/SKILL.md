---
name: b36-intellij-plugin
description: "Implement and certify an IntelliJ Platform plugin for repository assessment migration preview source-target navigation diagnostics quick fixes ownership review and local evidence workflows."
---

# Skill 1289: b36-intellij-plugin

## Use this skill when

- Java, Kotlin, Spring, Gradle, or Maven developers need migration workflows inside IntelliJ IDEA.
- A representative customer workflow must be completed without relying on the web console for every action.

## Domain-specific risks and invariants

- IDE write actions, PSI changes, indexing, dumb mode, and plugin compatibility can corrupt projects or freeze the editor.
- The plugin must not expose customer source, secrets, or local file paths through telemetry.

## Workflow

1. Lock exact IntelliJ Platform, JDK, Gradle IntelliJ plugin, supported IDE editions, and OS matrix.
2. Implement project service, tool windows, actions, notifications, editor gutters, diff viewers, source-map navigation, and protocol client.
3. Use PSI/write-command APIs for edits and preserve undo/redo, document versions, formatting, and protected ownership.
4. Implement local preview, diagnostics, quick fixes, affected tests, review comments, and evidence links.
5. Package, sign, install, upgrade, downgrade, and uninstall the plugin in real IDE harnesses.

## Required repository outputs

- IntelliJ plugin module, signed distribution manifest, permissions manifest, compatibility matrix
- UI tests, PSI/write-action tests, startup/performance measurements, privacy evidence
- Representative Java/Spring developer journey evidence

## Verification

- Build with the locked IDE SDK and run plugin verifier or equivalent compatibility checks.
- Run IDE integration tests in smart and dumb mode, with large projects and cancelled tasks.
- Verify undo/redo, no unrelated formatting, protected-region preservation, and no UI-thread blocking.
- Inspect network and telemetry output for source or secret leakage.

## Stop and escalate when

- Required PSI operation would bypass write-command or undo semantics.
- The plugin freezes the UI, corrupts indexes, or cannot support the declared IDE range.
- A quick fix cannot prove document and artifact freshness.
- Signing, distribution, or privacy evidence is missing.

## Definition of done

- A real IntelliJ user completes the certified workflow end to end.
- The plugin installs, upgrades, downgrades, and uninstalls safely.
- P0 navigation, preview, fix, test, ownership, and review flows pass.
- Performance, privacy, and compatibility thresholds are met.
