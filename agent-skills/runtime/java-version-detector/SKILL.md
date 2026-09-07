---
name: java-version-detector
description: Determine Java source, target, release, toolchain and runtime evidence for ELMOS. Use whenever a health report or migration plan needs current or candidate JDK versions.
---
# Java Version Detector

## Workflow
1. Inspect Maven compiler release/source/target, Java properties, Gradle compatibility and toolchains.
2. Keep declared build level separate from Workspace runtime `java -version` evidence.
3. Detect contradictory module levels and preview/incubator usage.
4. Return `INCONCLUSIVE` when no authoritative level exists.

## Acceptance
- Normalize `1.8` to `8` without rewriting source evidence.
- Never infer the project JDK solely from the scanner process.
- Target 17/21/25 selection remains an organization policy decision.

