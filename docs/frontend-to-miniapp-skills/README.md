# Frontend to MiniApp Skills Integration

This directory records the repository installation of `elmos.frontend-to-miniapp.skills` version `1.0.0`.

- Trusted archive: `skills/subskills/elmos-frontend-to-miniapp-skills-v1.0.0.zip` (`sha256:e8fabbe19f96a432e3ba77470e1c35a000cc683cd4ac0c084bbabcf31df79d82`)
- Canonical extracted source: `skills/elmos-frontend-to-miniapp-skills-v1.0.0/`
- Installed names: 22 exact source names under both `agent-skills/runtime/` and `.agents/skills/`
- Compiled contract: `compiled-contract.json` in each installed Skill plus this directory's aggregate `compiled-contracts.json`
- Runtime authority: `engines/frontend-client-engine` — `npm run miniapp` (`dist/src/miniapp-cli.js`), `handleMiniappSkillRequest` / `runMiniappSkillJson`, full flow `runMiniappConversion`, strict package flow `runMiniappPackageConversion`, single-Skill `executeMiniappSkill`
- Canonical package request entry: source snake_case Schema `skills/elmos-frontend-to-miniapp-skills-v1.0.0/schemas/conversion-request.schema.json`; CLI `npm run miniapp -- package`; handler envelope `{"schemaVersion":"1.0","action":"run-package","packageInput":...}`; validator `validateMiniappPackageConversionInput`; compiler `compileMiniappPackageConversionInput`
- Component adapter: `engines/component-dialect-engine` — `npm run miniapp-worker` (`dist/miniapp-worker.js`), `handleMiniAppWorkerRequest` / `runMiniAppWorkerJson`, `emitPlatformMiniApp`
- Current evidence: bounded runtime `DECLARED`, external `NOT_RUN`, certification `NOT_CERTIFIED`
- Digest-bound local evidence projection: `local-runtime-evidence.json`
- Qualification receipt source: `artifacts/frontend-to-miniapp/local-runtime-receipt-v1/receipt.json`; it is machine-local, is not committed, and absence keeps the portable repository state `DECLARED`

The importer validates the ZIP before extraction: fixed digest and root, normalized unique paths, regular-file type, exact modes, per-entry and total size limits, compression ratio, CRC/readability, exact file count, and archive-to-source byte binding. It then verifies `CHECKSUMS.sha256`, YAML/JSON manifest parity, package inventory, 22 Skill frontmatters, all 14 Draft 2020-12 Schemas against their exact indexed fixtures (including format checks), 40 task IDs, output contracts, and the 53-edge acyclic dependency graph without executing any source-package script.

`--refresh-owned` only refreshes identity-verified owned trees and never creates execution evidence. Run `--qualify-local` explicitly to execute the fixed trusted repository suite, capture raw logs, dynamically parse test counts, record exact executable paths/versions, OS/architecture, working directories and observed timing, and atomically update the implementation-bound receipt. The two builds execute the canonical frontend/component `node_modules/.bin/tsc` entrypoint inodes and the component tests execute its canonical `node_modules/.bin/jest` entrypoint inode; the receipt binds each invocation path, canonical execution path, version, entrypoint byte count, and SHA-256 digest. These entrypoint digests do not claim a digest of the entire dependency tree. Then run `--refresh-owned` and `--check` to project and verify that receipt in the installed contracts. The receipt and its `LOCAL_EXECUTED` projection are host-specific working-tree evidence: do not commit them. An environment or project-tool byte mismatch remains a hard failure and is never treated as execution success.

Use `--closeout-portable` before a portable release commit. Under the fixed receipt writer lock it validates and atomically moves any host receipt into an owned `0700` system temporary archive, transactionally refreshes every owned tree to `DECLARED`, and runs the installation check. An absent receipt is valid and remains `DECLARED`. On failure it restores the original receipt only when the archived inode still matches and the destination remains absent; it never overwrites a competing object, and reports the archive path for recovery. The canonical `make frontend-to-miniapp-skills` target installs an EXIT/signal closeout handler so success and ordinary command failure both attempt this portable projection; a closeout failure remains a failing result and must be resolved before staging.

These Skills now have callable local handlers for source discovery, typed UI/MiniApp IR, planning, four native candidate generators, checkpoints, bounded repair planning, evidence reporting and a strict CLI. Local execution is not proof of official MiniApp builds, browser/emulator/device journeys, privacy and permission review, accessibility, visual and business equivalence, upload/review/release, independent holdout evidence, or reverse MiniApp-to-frontend routes. Only the conservative Batch 32 gate can raise readiness.

The `package` CLI reads one exact wrapper with `packageRequest`, `files`, `versionBindings`, and `evidenceBindings`; it never reads a source tree from disk or executes package scripts. The equivalent structured handler action is `run-package` with that wrapper in `packageInput`.

Verify the immutable archive, extracted source, compiled contracts, documentation, and byte-identical dual roots with:

```sh
uv run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 python tooling/integrate_frontend_to_miniapp_skills.py --check
```

Run the repository target with:

```sh
make frontend-to-miniapp-skills
```
