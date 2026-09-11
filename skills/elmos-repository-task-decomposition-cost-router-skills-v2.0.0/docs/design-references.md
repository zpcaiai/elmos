# Design references

This package is an original Elmos integration design. It borrows architectural ideas, not source code, from current research and open tooling.

- **AdaPlan-H — From Coarse to Fine: Self-Adaptive Hierarchical Planning for LLM Agents (ACL Findings 2026)**  
  https://aclanthology.org/2026.findings-acl.77/  
  Adopted idea: progressive coarse-to-fine planning and adaptive task granularity.

- **SWE-RPG — A Unified Issue Resolution Benchmark for Requirement Clarification, Planning, and Code Generation for Coding Agents (2026)**  
  https://arxiv.org/abs/2608.09072  
  Adopted idea: requirement clarification and implicit-requirement recovery must be evaluated separately from code generation.

- **Repository Intelligence Graph (RIG) (2026)**  
  https://arxiv.org/abs/2601.10112  
  Adopted idea: deterministic, evidence-backed architectural/build/test graph as planning context.

- **GNNVerifier — Graph-based Verifier for LLM Task Planning (2026)**  
  https://arxiv.org/abs/2603.14730  
  Adopted idea: structural plan validation should detect graph-level defects that prose self-review may miss. Elmos v2 uses deterministic graph verification by default; a learned graph verifier is an optional future extension.

- **Agent-as-a-Router / ACRouter (2026)**  
  https://github.com/LanceZPF/agent-as-a-router  
  Adopted idea: execution feedback, verifier results and memory should update future decisions.

- **RouteLLM**  
  https://github.com/lm-sys/RouteLLM  
  Adopted idea: calibrated cost/quality routing and replaceable router algorithms.

- **OmniRoute**  
  https://github.com/diegosouzapw/OmniRoute  
  Adopted ideas in the model-routing package: provider health, quota, cache/context awareness and dispatch strategies.

- **9Router**  
  https://github.com/decolua/9router  
  Adopted ideas in the model-routing package: capability filtering, sticky/fallback dispatch and provider/account cost controls.
