# Compatibility and Installation

## 1. Skill layout

The canonical directories in this package use one directory per Skill with a required `SKILL.md`:

```text
skills/<skill-name>/SKILL.md
```

The package includes hard-copy mirrors for repository installation:

```text
.agents/skills/<skill-name>/SKILL.md   # Codex
.claude/skills/<skill-name>/SKILL.md   # Claude Code
```

The canonical source remains `skills/`; edit it and run `scripts/repack.py` to refresh mirrors and archives.

## 2. Install

### macOS/Linux

```bash
bash scripts/install.sh --target /path/to/elmos --both
```

Options:

```text
--codex          install only .agents/skills
--claude         install only .claude/skills
--both           install both (default)
--target PATH    repository root
--force          replace existing package-owned skill directories
--dry-run        print actions
```

### Windows PowerShell

```powershell
./scripts/install.ps1 -Target C:\path\to\elmos -Mode Both
```

### Manual

Copy each directory under `skills/` to the relevant repository skill root. Do not flatten the directories.

## 3. Codex parity context baseline

The compatibility fixture as of **2026-08-19** is:

```yaml
context_window_tokens: 1050000
max_output_tokens: 128000
```

This package treats it as a dated test/default profile. Runtime code must query `ModelCapabilitySnapshot` and must not assume the same value for every Codex or non-Codex model forever.

## 4. Different model sizes

When the chosen model has less capacity than the task plan:

1. report incompatibility;
2. offer or perform model reroute if tenant policy allows;
3. partition by task/repository domain;
4. rank and pack;
5. structurally compact;
6. rehydrate exact evidence as needed;
7. run context integrity gates.

Never silently truncate.

When a model has a larger future context, Elmos may load more evidence but should still rank, deduplicate and reserve output/tool headroom.

## 5. Provider neutrality

The package does not require a single OCR, ASR, vision or LLM provider. Adapters expose:

```text
capabilities
privacy/region
accuracy profile
latency
price
input/output limits
usage receipts
health
```

Routing uses tenant policy and can prefer local/private models. Provider-specific output is normalized into common schemas.

## 6. Repository adaptation

The Skills intentionally do not force a language or infrastructure stack. During Phase 0:

- preserve existing Elmos framework and conventions;
- map logical tables to existing aggregates;
- reuse task/workflow/identity/storage if adequate;
- create ADRs for deviations;
- retain API semantics and invariants;
- avoid microservice decomposition without operational need.

## 7. Schema/version compatibility

- JSON schemas use Draft 2020-12.
- Runtime events include independent schema versions.
- Package manifests and checkpoints are immutable.
- Backward-compatible fields are optional/additive.
- Breaking fields create a new schema version and migration.
- Historical tasks retain the model capability/policy/schema snapshots used at execution.

## 8. Mirroring rules

`skills/` is canonical. `.agents/skills` and `.claude/skills` must be byte-equivalent mirrors for `SKILL.md` and `references/`. The validator checks this.

## 9. Line endings and paths

- UTF-8 without BOM is preferred.
- Use POSIX-style normalized relative paths in manifests.
- Preserve original display names separately.
- Do not leak or store local absolute paths.
- Treat case/Unicode collisions explicitly because target file systems differ.

## 10. Package validation

```bash
python3 scripts/validate_package.py
```

It checks:

- exactly 50 canonical Skills;
- YAML frontmatter `name` and `description`;
- path/name consistency;
- dependency existence;
- JSON Schema validity;
- YAML parseability;
- 100 trigger-eval rows;
- mirror equivalence;
- required files;
- no obvious placeholders.

## 11. Repack

```bash
python3 scripts/repack.py
```

The script validates, refreshes mirrors, writes `CHECKSUMS.sha256`, and builds ZIP/TAR.GZ next to the package root.
