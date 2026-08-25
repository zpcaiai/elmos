# AGENTS.md — Elmos Frontend → MiniApp

## Required workflow

When a task asks to convert, analyze, test, repair, or release a frontend project for WeChat, Alipay, Douyin, or Xiaohongshu miniapps:

1. Start with `$frontend-to-miniapp-orchestrator` unless the request explicitly names a narrower skill.
2. Read `skill-manifest.yaml`, then only load the selected skill and its referenced files.
3. Treat the source repository as read-only until a conversion workspace is created.
4. Validate all structured artifacts against `schemas/`.
5. Never claim completion without native build evidence, test evidence, and `migration-evidence.json`.
6. Never silently drop unsupported behavior. Classify it A/B/C/D/E.
7. Never place real platform secrets in client code, fixtures, logs, or reports.
8. Do not perform real payment, refund, upload, review submission, or production release without explicit approval.
9. Prefer fixing IR, mapping rules, or adapters over hand-editing generated files.
10. Run `./verify.sh` after changing this skills package.

## Canonical paths

- Skills: `.agents/skills/`
- Architecture: `docs/ARCHITECTURE.md`
- First tasks: `docs/FIRST-40-TASKS.md`
- Gates: `docs/ACCEPTANCE-GATES.md`
- Schemas: `schemas/`
- Fixtures: `fixtures/`

## Completion language

Use `passed`, `blocked`, `failed`, `unknown`, or `approved`. Do not use “fully implemented” unless all required gates are backed by current artifacts and hashes.
