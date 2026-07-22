# ELMOS combined Skill pack — M1–M45 and Product B34–B55

This repaired package is an explicit dual-namespace catalog. It is not one
linear Batch 1–55 certification series.

## Inventory

- Migration Packs M1–M45: **820 Skills**
- Product commercialization B34–B55: **1,004 Skills**
- Total installable contracts: **1,824 Skills**
- Deterministic aliases for names over 64 characters: **1,015**

Every Skill passes the official `skill-creator` validator and includes an
invocable `agents/openai.yaml` interface. `source_name` is retained in the
manifest for every deterministic alias.

## Completion boundary

- M1–M28: 448 normalized implementation-planning Skills; exact original source
  bundles were unavailable and M21–M28 contain generic recovered domains.
- M29–M45: 372 repository contracts.
- Product B34–B39: 236 complete-source contracts.
- Product B40A: 16 approved conversation-design contracts.
- Product B40B–B55C: 752 generated planning-edition contracts requiring domain
  owner refinement.
- Customer, provider, production and certification evidence: `NOT_RUN`.

Consequently, structural validation is `PASS`, while overall completion remains
`NOT_COMPLETE`. Static Skill validation never certifies implementation or field
operation.

## Validate

```bash
./validate.sh
```

## Install

The target directory is mandatory. By default, only repository, complete-source
and approved-design contracts are installed:

```bash
./install.sh /absolute/path/to/codex/skills
```

Use `--include-non-authoritative` only after accepting the normalized-source and
planning-edition limitations. Existing destinations fail preflight unless
`--overwrite` is supplied; overwritten Skills are moved to a recoverable backup.
