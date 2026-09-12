---
name: "elmos-teaching-subsystem"
description: "Generate diagrams, analyze project structure, create guided tours, manage code annotations, run teaching scenarios, and export reports using the teaching subsystem engine."
---

# ELMOS Teaching Subsystem

The teaching subsystem orchestrator skill provides a unified interface for generating project documentation, architecture diagrams, interactive guided tours, and structured teaching scenarios. It leverages the underlying teaching subsystem engine to parse codebases and translate raw analysis into instructional materials.

## When to Use
- You need to generate comprehensive documentation for a project.
- You need to create an interactive tour to explain codebase architecture or logic flows.
- You want to extract and map out the data flows, threat models, and sequence diagrams of existing code.
- You need to prepare structured teaching scenarios for developer onboarding or technical reviews.

## Capabilities
- **Diagram Generation:** Create architecture, module dependency, call sequence, data flow, ER, threat model, and mindmap diagrams.
- **Project Analysis:** Run pattern recognition, tech stack detection, technical debt heatmap generation, code ownership tracking, API index creation, and SBOM extraction.
- **Guided Tours:** Build and orchestrate interactive step-by-step walkthroughs of the codebase.
- **Code Annotations:** Manage contextual annotations that map code snippets to educational notes.
- **Debug Workbench:** Interactive execution environment for demonstrating issues and tracing execution.
- **Teaching Scenarios:** Run fully structured teaching scenarios for onboarding or deep-dives.

## Usage
Interact with the teaching subsystem engine via the `elmos-teaching` CLI. 

- `elmos-teaching diagram <type> --source <path>`: Generate a diagram. Types include `architecture`, `module`, `sequence`, `dataflow`, `er`, `threat`, `mindmap`.
- `elmos-teaching analyze <target> --format json`: Run analysis for `pattern`, `tech-stack`, `debt`, `ownership`, `api`, `sbom`.
- `elmos-teaching tour create --target <module> --output tour.json`: Generate a guided tour.
- `elmos-teaching export <format>`: Export generated materials to Markdown, HTML, or PDF.

## Engine Location
`engines/teaching-subsystem-engine/`

## Integration
This skill integrates closely with `elmos-diagram-generation`, `elmos-guided-project-tour`, and `elmos-teaching-scenarios` to orchestrate full learning experiences.
