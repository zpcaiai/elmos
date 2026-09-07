---
name: architecture-risk-scanner
description: Scan Java source for architecture and complexity modernization risks. Use for package cycles, oversized types, branch density, deprecated APIs, static coupling, or legacy boundary findings.
---
# Architecture Risk Scanner

## Workflow
1. Build a package import graph from bounded source text.
2. Detect stable package cycles and retain their complete paths.
3. Flag oversized types, high branch density and known legacy namespace use.
4. Label heuristic results as review findings, not compiler facts.

## Acceptance
- Results are stable across checkout locations.
- Generated/build output is excluded.
- Thresholds and scanner version are recorded.

