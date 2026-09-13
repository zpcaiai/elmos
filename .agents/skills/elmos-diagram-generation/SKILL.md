---
name: "elmos-diagram-generation"
description: "Generate architecture diagrams, data flow diagrams, ER diagrams, sequence diagrams, module dependency graphs, threat model diagrams, and mindmaps from project analysis."
---

# ELMOS Diagram Generation

The unified diagram generation skill transforms static project analysis into rich, visual representations. It acts as the pipeline between the project intelligence engine's raw extracted data and final rendered visualizations.

## When to Use
- You need visual architecture representations to explain complex system topologies.
- You are documenting database schemas and require ER diagrams.
- You are reviewing security and need threat model diagrams based on data flows.
- You need to visualize the dependency graph of modules to identify cyclic dependencies or refactoring candidates.

## Capabilities
- **Architecture Diagrams:** C4 models (Context, Container, Component, Code) generated automatically from structural analysis.
- **Data Flow Diagrams (DFD):** Visualizes the movement of data between components and external systems.
- **ER Diagrams:** Extracts database schema definitions and object relationships.
- **Sequence Diagrams:** Traces runtime or static call chains across system boundaries.
- **Module Dependency Graphs:** Highlights import/export relationships and tight coupling.
- **Threat Model Diagrams:** Annotates DFDs with STRIDE categories and trust boundaries.
- **Mindmaps:** Generates hierarchical overviews of project structure or domains.

## Export Formats
Diagrams can be exported to multiple formats:
- Mermaid (default, easily embeddable in Markdown)
- SVG (vector rendering)
- HTML (interactive visualization)
- PPTX (for presentations)
- JSON (raw AST representation)

## Usage
The diagram generation pipeline is accessible through the teaching CLI or directly via the diagram rendering APIs:

```bash
elmos-teaching diagram architecture --level container --format mermaid
elmos-teaching diagram dataflow --target src/auth --format svg
```

## Bounded Limits and Safety
- Diagram generation is bounded to prevent OOM errors on massive graphs (max 1000 nodes per render).
- Automatically clusters heavily connected subgraphs.
- Sanitizes all textual inputs before inserting them into Mermaid/SVG templates to prevent injection.

## Engine Location
`engines/project-intelligence-engine/` and `engines/teaching-subsystem-engine/`

## Integration
Relies on data provided by `elmos-project-structure-analysis` and feeds output to `elmos-guided-project-tour`.
