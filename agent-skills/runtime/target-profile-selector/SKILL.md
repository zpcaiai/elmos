---
name: target-profile-selector
description: Select an ELMOS Java and Spring modernization target from health evidence and organization policy. Use for Java 17/21/25, Spring target lines, Jakarta namespace or build strategy decisions.
---
# Target Profile Selector

## Workflow
1. Consume an immutable health report and allowed organization targets.
2. Default to Java 21 only when policy allows it.
3. Require explicit certification assumptions for Java 17 or 25 alternatives.
4. Separate target line selection from exact dependency versions.

## Acceptance
- Unknown source JDK creates an evidence gate.
- The newest release is never selected implicitly.
- Output includes assumptions and evidence status.

