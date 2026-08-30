# Cross-Harness Compatibility

Elmos SHOULD import useful external project instructions and skills without inheriting unsafe precedence semantics.

## Import families

- AGENTS.md-style repository instructions
- Claude/Codex-compatible skill markdown where contracts can be normalized
- Cursor rule files
- Cline rule files
- GitHub/Copilot instruction files
- Windsurf-style rules
- OMP-style rules/skills when applicable

## Normalization

External content → `RuleIR` or `SkillManifest`.

Imported artifacts MUST record:

- source family;
- original path;
- source digest;
- normalized version;
- authority;
- scope;
- unsupported fields;
- conflicts.

## Security

Imported prompts/rules MUST NOT automatically gain write/exec authority.
Authority is assigned by Elmos policy, not by source-file claims.
