# Portable Skills and OpenAI Plugin Compiler

## Objective

Compile one evidence-bound Skill IR into Agent Skills, OpenAI Plugins, Codex, Claude Code, Pi, OpenClaw, Gemini CLI, OpenCode and Continue without letting host syntax become canonical semantics.

## Required semantic objects

- `SkillDefinition`, `TriggerContract`, `InstructionGraph`;
- typed tools and Environment-owned authority;
- content-addressed scripts, references and assets;
- host capability profile and semantic-loss ledger;
- trigger evaluation dataset and cross-host normalized traces;
- package signature, SBOM/AIBOM, publisher identity and revocation.

## Release boundary

A generated folder is E0. Host parsing is E1. Native task and negative-trigger execution is E2/E3. Cross-host differential and upgrade/rollback evidence is E4. Customer/production certification remains E5/P05.
