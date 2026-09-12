---
name: "elmos-guided-project-tour"
description: "Create interactive guided tours of codebases for onboarding, architecture review, security audit, and custom walkthroughs."
---

# ELMOS Guided Project Tour

This skill allows the ELMOS agent to dynamically generate, customize, and orchestrate interactive, step-by-step walkthroughs of a codebase. Tours help ground developers in large projects by walking them through logical flows, architectural decisions, and critical components in a narrative fashion.

## When to Use
- Onboarding a new developer to a specific microservice or library.
- Conducting an asynchronous architecture review.
- Performing a guided security audit of critical paths (e.g., authentication flow).
- Reviewing the API surface area and its underlying implementation.

## Capabilities
- **Tour Scenarios:** Built-in templates for:
  - `ARCHITECTURE_OVERVIEW`
  - `DATA_FLOW_WALKTHROUGH`
  - `SECURITY_AUDIT`
  - `API_SURFACE_REVIEW`
  - `ONBOARDING`
- **Step Structure:** Each tour step consists of a title, description, code snippet reference, file path, line numbers, and associated diagram segments.
- **Progress Tracking:** Tracks the user's progression through the tour, allowing resuming and state persistence.
- **Annotation Integration:** Links code annotations with tour steps to provide context without polluting source code.

## Usage
Generate and manage tours using the CLI:

```bash
elmos-teaching tour create --scenario ONBOARDING --target src/ --output my-tour.json
elmos-teaching tour run --file my-tour.json
elmos-teaching tour status
```

## Engine Location
`engines/teaching-subsystem-engine/`

## Integration
Integrates with `elmos-diagram-generation` to embed visual context within tour steps, and utilizes `elmos-project-structure-analysis` to determine the most critical paths to include in the tour.
