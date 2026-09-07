# Scripts

## Requirements

```bash
python3 -m pip install PyYAML jsonschema
```

## Validate

```bash
python3 scripts/validate_package.py
```

Checks canonical Skill count/frontmatter/contracts/dependencies, schemas, YAML, trigger evaluation rows, required docs and both repository mirrors.

## Install

```bash
bash scripts/install.sh --target /path/to/elmos --both
```

or on PowerShell:

```powershell
./scripts/install.ps1 -Target C:\path\to\elmos -Mode Both
```

Existing skill directories are not replaced unless `--force` / `-Force` is supplied.

## Repack

```bash
python3 scripts/repack.py
```

This refreshes `.agents/skills` and `.claude/skills`, validates, writes checksums, and creates ZIP/TAR.GZ next to the package root.
