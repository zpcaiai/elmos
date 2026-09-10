# Elmos Proof-Driven Certification Skill Package

Industrial Antigravity/Codex Agent Skill for building Elmos Execution Truth & Independent Certification infrastructure.

## What this package does

This skill forces implementation toward a trust-separated certification architecture where:

- Builder agents may modify code and request verification.
- Authority freezes immutable source snapshots and issues verification tickets.
- Truth Runner performs real deterministic execution and emits factual evidence.
- OPA is the deterministic authorization gate.
- Production hardening adds SPIFFE/SPIRE workload identity, mTLS, KMS, Sigstore/in-toto attestations, immutable evidence storage, Temporal isolated workers, Hidden Test Vault, mutation/sabotage testing, Ethen semantic audit, and deployment digest binding.

The primary security property is: **an AI agent can lie in text or create fake files, but it cannot manufacture authoritative certification.**

## Install into an Antigravity project

```bash
unzip elmos-proof-driven-certification-skill.zip
cd elmos-proof-driven-certification-skill
./install.sh /path/to/your/elmos-project
```

This installs the skill at:

```text
<project-root>/.agents/skills/elmos-proof-driven-certification/
```

Optional: install the persistent AGENTS.md rules too:

```bash
./install.sh /path/to/your/elmos-project --agents
```

The installer never overwrites an existing `.agents/AGENTS.md`; it appends a guarded Elmos block only when `--agents` is supplied.

## Validate the package

```bash
./skill/scripts/validate_package.sh ./skill
```

If `opa` is installed, the validator also runs the bundled Rego policy tests.

## Scaffold implementation work packages

After the skill is installed, from your Elmos repository root:

```bash
python3 .agents/skills/elmos-proof-driven-certification/scripts/scaffold_trust_core.py --root .
```

By default the scaffolder only creates missing directories and starter files. It does not overwrite existing code. Use `--dry-run` to preview.

## Suggested Antigravity prompt

```text
Use the elmos-proof-driven-certification skill. Implement the next incomplete work package in dependency order. Do not claim completion from generated evidence. Run the package validation and all available tests, and report exact commands, exit codes, test counts, blockers, and remaining work.
```

## Package contents

```text
skill/
├── SKILL.md
├── references/
├── policies/base/
├── schemas/
├── templates/
└── scripts/
```

Start with `skill/SKILL.md`.
