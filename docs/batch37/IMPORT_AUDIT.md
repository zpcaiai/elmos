# Batch 37 complete-package import audit

## Source examined

The supplied directory `migration-platform-batch20-b29-b30-b31-b32-b33-b34-b35-b36-b37-complete` was treated as an input specification, not as an overwrite of the existing ELMOS repository. Its independent Batch 20 application scaffold was not copied over the richer current multi-module implementation. Batch 29–36 assets were compared and the existing repository variants were retained where they already had stronger gates, executable modules, or broader tests.

## Source-package inconsistencies

- The directory contains 668 non-cache files, while `FILE_MANIFEST.txt` lists 624 paths.
- The manifest omits 73 non-cache files, principally the completed Batch 37 closure assets.
- The manifest also lists 29 generated `__pycache__/*.pyc` paths that are absent and must not be distribution inputs.
- `BATCH37_VALIDATION.md` reports 20 Skills, 10 Schemas, and 7 tests, while the actual completed Batch 37 payload contains 36 Skills, 25 Schemas, 27 templates, 25 Python tools, and 19 original toolkit tests.

The stale source manifest and report are therefore preserved only as provenance. Repository validation derives counts from actual files and excludes generated caches.

## Imported and repaired

- 20 numeric Skills (`1305`–`1324`) and 16 non-conflicting supplemental Skills (`B37-X01`–`B37-X16`).
- 25 Draft 2020-12 Schemas, 27 templates, 25 deterministic Python tools, two toolkit suites, and the Batch 37 Make targets.
- Generated and validated `agents/openai.yaml` metadata for all 36 Skills.
- Protected Batch 37 from the generic Batch 38–45 generator and shared compatibility toolkit.
- Hardened both gates so research/experimental packs report `NOT_CERTIFIED`; closure completion can only be true for an explicitly requested, fully passing certification.
- Replaced “any nonempty corpus file” with digest-bound, independently executed corpus manifests carrying authorization and evidence references.
- Added explicit `PASSED` requirements for external and closure evidence before certification can be issued.
- Added the executable `modules/extension-marketplace` core and an experimental local evidence pack. External publisher, production signing, holdout, representative, provider, private/offline, DR, settlement, legal/support, and EOL evidence remains `NOT_RUN`.

The superseded generic Batch 37 files are recoverably retained under `artifacts/batch37-legacy-generated-backup-20260722/` and are not part of the active Skill surface.
