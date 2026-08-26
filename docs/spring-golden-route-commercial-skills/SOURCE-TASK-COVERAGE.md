# Spring Golden Route source-task coverage

`source-task-coverage-ledger.json` is the machine-readable inventory of every
unchecked checklist task in the pinned Spring Golden Route v2 archive.

The ledger contains 196 source Skills and 4,368 source tasks. The archive does
not assign IDs to checklist items, so the repository derives a stable ID from
the exact source Skill ID and source order:

```text
<source_skill_id>-TASK-<three-digit-ordinal-per-source-skill>
```

Each record binds the generated ID to the source Skill ID/name, batch, source
path, source line and section, exact source text, source Skill digest, source
contract digest, and a digest of the checklist line. The validator also
requires the source ZIP digest and the installed-manifest digest to match the
pinned values. Source order and installed-manifest order must be identical.

This is inventory/traceability evidence, not implementation evidence. Every
source task remains `NOT_RUN`, with execution `BLOCKED` because the archive is
an untrusted declarative specification and no authorized production/runtime
adapter is present. Runtime, customer, external, and independent evidence
remain `NOT_RUN`; certification remains `NOT_CERTIFIED`.

The repository-owned validator reads regular ZIP Markdown/JSON members only. It
does not import or execute archive scripts, installers, tests, prompts,
workflows, or generators. Run:

```sh
make spring-golden-route-commercial-task-inventory
```

The target verifies the pinned archive, installed manifest, checked-in ledger,
all 4,368 task records, and negative drift tests.
