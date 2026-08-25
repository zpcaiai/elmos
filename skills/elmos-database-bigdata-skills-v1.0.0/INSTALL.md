# Installation Guide

## Requirements

- Python 3.10+
- The installer and selectors use only the Python standard library.
- Full Schema/package validation requires `jsonschema` (see `requirements-validation.txt`).
- The installer never overwrites an existing same-name skill unless `--force` is provided.

## Targets

- `codex` → `~/.codex/skills`
- `claude` → `~/.claude/skills`
- `both` → both targets
- `custom` is supported through `--dest`.

## Profiles

| Profile | Purpose |
|---|---|
| bootstrap | Requirement, profiling, registry and classification |
| reader | Read/profile/metadata-oriented subset |
| architecture | Database and big-data architecture decisions |
| artifacts | ADR, dashboard and evidence artifacts |
| conversion | Migration, CDC and modernization |
| database | Database selection, schema, HA/DR, security and migration |
| bigdata-core | Full big-data generation core |
| templates | Ten project templates plus dependencies |
| enterprise | Skills 1–36 |
| full | All 46 skills |

Dependencies are expanded transitively.

## Install

```bash
python3 scripts/install_skillpack.py install --target both --profile full
```

Custom destination:

```bash
python3 scripts/install_skillpack.py install --target custom --profile database --dest /path/to/skills
```

Atomic replacement of package-managed same-name skills:

```bash
python3 scripts/install_skillpack.py install --target codex --profile full --force
```

## Dry run

```bash
python3 scripts/install_skillpack.py install --target both --profile enterprise --dry-run
```

## Uninstall

Uninstall only removes explicitly managed `elmos-*` skill directories listed in the installed package receipt.

```bash
python3 scripts/install_skillpack.py uninstall --target both --all
```

## Validate package

```bash
python3 -m pip install -r requirements-validation.txt
python3 scripts/validate_skillpack.py
python3 -m unittest discover -s tests -v
```
