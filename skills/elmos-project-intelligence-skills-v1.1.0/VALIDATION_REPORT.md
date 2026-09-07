# Validation Report

## Package identity

- Package: `elmos-project-intelligence-skills`
- Version: `1.1.0`
- Validation date: `2026-08-20`
- Status: **PASS**

## Structural and semantic validation

| Check | Expected | Result | Status |
|---|---:|---:|---|
| Skills | 50 | 50 | PASS |
| Epic records | 50 | 50 | PASS |
| Implementation batches | 15 | 15 | PASS |
| Backlog tasks | 500 | 500 | PASS |
| Acceptance scenarios | 248 | 248 | PASS |
| JSON Schemas | 14 | 14 parsed | PASS |
| Schema/example validation pairs | 10 | 10 | PASS |
| Contract files | 7 | 7 parsed/inspected | PASS |
| Missing Skill dependencies | 0 | 0 | PASS |
| Skill dependency cycles | 0 | 0 | PASS |
| Cross-batch forward hard dependencies | 0 | 0 | PASS |
| Duplicate Skill/Epic/Task/AC identifiers | 0 | 0 | PASS |
| YAML/JSON parse failures | 0 | 0 | PASS |
| Validator warnings | 0 | 0 | PASS |

Strict validation command:

```bash
python3 scripts/validate_skillpack.py --strict-jsonschema
```

Observed result:

```json
{
  "skills": 50,
  "epics": 50,
  "tasks": 500,
  "acceptance_scenarios": 248,
  "batches": 15,
  "jsonschema_enabled": true,
  "warnings": [],
  "errors": [],
  "status": "PASS"
}
```

## Automated tests

```bash
python3 -m unittest discover -s tests -v
```

| Test | Status |
|---|---|
| `test_debug_profile_contains_online_debug_stack` | PASS |
| `test_dry_run_installer` | PASS |
| `test_profiles_reference_real_skills` | PASS |
| `test_real_install_uses_canonical_skill_names` | PASS |
| `test_validator_passes` | PASS |

Summary: **5/5 PASS**.

## Debug profile installation verification

The `debug` profile resolves to **28 Skills**, including all six v1.1.0 debug capabilities and their transitive prerequisites.

Verified on a clean temporary repository for both hosts:

- Codex target: `.agents/skills/` — 28 canonical Skill directories;
- Claude Code target: `.claude/skills/` — 28 canonical Skill directories;
- shared specifications: `.elmos/skillpacks/elmos-project-intelligence/` — copied successfully;
- required debug Skills present on both targets:
  - `elmos-debug-adapter-gateway`;
  - `elmos-debug-sandbox-orchestration`;
  - `elmos-online-debug-workbench`;
  - `elmos-debug-learning-copilot`;
  - `elmos-debug-record-replay`;
  - `elmos-distributed-debug-correlation`.

## Debug-specific quality gates covered by the package

- fixed project revision and version-pinned runtime/adapter;
- DAP/CDP capability negotiation rather than assumed universal support;
- ephemeral non-root sandbox or microVM, read-only root filesystem and no Docker Socket;
- egress deny-by-default, resource quotas, kill switch and cleanup attestation;
- production attach denied by default, with audited break-glass policy only;
- Debug Console separated from arbitrary shell access;
- read-only Evaluate/Watch/conditional breakpoint policy by default;
- server-side redaction of variables, logs, HTTP, SQL, messages and replay data;
- Observe, Guided, Challenge, Free and Compare learning modes;
- Frame/variable/side-effect explanations linked to code and project evidence;
- R0–R3 replay capability levels with explicit downgrade semantics;
- distributed/async correlation that preserves uncertainty instead of fabricating causality;
- Source/IR/Target comparison for Elmos conversion verification.

## Distribution verification

A reproducible ZIP was built, extracted into a clean directory and checked independently.

| Check | Result | Status |
|---|---|---|
| ZIP central-directory / compressed-data integrity | No errors | PASS |
| Archive file entries | 336 | PASS |
| `MANIFEST.sha256` entries | 335 non-manifest files | PASS |
| Extracted manifest verification | Every listed file `OK` | PASS |
| Strict validator from extracted package | 50 Skills, 500 tasks, 248 AC, zero warnings/errors | PASS |
| Automated tests from extracted package | 5/5 | PASS |
| Extracted `debug` profile clean install | 28 Skills to each of Codex and Claude Code | PASS |
| Six required debug Skills on both hosts | Present | PASS |

The formal archive is rebuilt after this report and manifest update, then subjected once more to the same integrity, manifest, strict-validation and test checks.
