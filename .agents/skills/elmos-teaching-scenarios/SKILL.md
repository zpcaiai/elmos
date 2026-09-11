---
name: "elmos-teaching-scenarios"
description: "Create and run structured teaching scenarios for developer onboarding, architecture review, security audit, and performance review."
---

# ELMOS Teaching Scenarios

This skill orchestrates comprehensive, interactive learning experiences. It ties together project analysis, guided tours, code annotations, and diagrams into a cohesive scenario designed to achieve specific learning objectives for developers.

## When to Use
- A new developer joins the team and needs a structured onboarding path through the codebase.
- The team is conducting an architecture review and needs a scenario that steps through key design decisions and data flows.
- Running a security audit walkthrough to educate the team on existing threat models.
- Reviewing performance bottlenecks through a guided tracing scenario.

## Capabilities
- **Scenario Templates:** Pre-defined templates tailored for onboarding, security, architecture, and performance.
- **Difficulty Levels:** Scenarios can be tailored (e.g., Beginner, Intermediate, Expert) to adjust the depth of information and complexity of the steps.
- **Step-by-Step Progression:** Orchestrates the flow from one topic to the next, ensuring prerequisites are met before diving into complex areas.
- **Learning Objectives:** Explicitly defines and tracks the goals the user should achieve by the end of the scenario.
- **Progress Tracking:** Monitors user engagement, completion rates, and allows users to pause and resume their sessions.

## Usage
Manage and execute teaching scenarios using the ELMOS CLI tools.

```bash
elmos-teaching scenario list
elmos-teaching scenario generate --template onboarding --level beginner --output scenario.json
elmos-teaching scenario run --file scenario.json
```

## Engine Location
`engines/teaching-subsystem-engine/`

## Integration
Heavily relies on `elmos-guided-project-tour` for the actual walkthroughs, `elmos-diagram-generation` for visual aids, and `elmos-project-structure-analysis` to contextualize the scenario content.
