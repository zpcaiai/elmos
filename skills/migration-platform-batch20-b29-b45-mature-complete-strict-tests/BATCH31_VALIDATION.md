# Batch 31 Validation

- Skills: 22/22 discovered and validated.
- Schemas: 6 JSON schemas meta-validated.
- Templates: 9 deterministic templates included.
- Python scripts compile successfully.
- Toolkit unit tests pass, including conservative fake-certification rejection.

## `/opt/pyvenv/bin/python3 scripts/batch31/validate_skill_bundle.py .agents/skills`

Return code: `0`

```text
OK: 22 Batch 31 skills
```

## `/opt/pyvenv/bin/python3 -m unittest tests/batch31/test_toolkit.py`

Return code: `0`

```text
/tmp/tmpzzsc3t7l/database-packs/mysql-to-postgresql
OK: /tmp/tmpzzsc3t7l/database-packs/mysql-to-postgresql
OK: /tmp/tmpzzsc3t7l/database-packs/mysql-to-postgresql/canonical-ir/model.json nodes=0
/tmp/tmpj74ysv0b/database-packs/oracle-to-postgresql
OK: /tmp/tmpj74ysv0b/database-packs/oracle-to-postgresql
OK: /tmp/tmpj74ysv0b/database-packs/oracle-to-postgresql/canonical-ir/model.json nodes=0
OK: 22 Batch 31 skills
```

## `/opt/pyvenv/bin/python3 -c import json, pathlib, jsonschema; root=pathlib.Path('.'); [jsonschema.validators.validator_for(json.loads(p.read_text())).check_schema(json.loads(p.read_text())) for p in (root/'schemas/batch31').glob('*.json')]; print('OK schemas')`

Return code: `0`

```text
OK schemas
```

## Merged repository regression

The combined repository passes:

- Batch 29 skill validation and 3/3 toolkit tests;
- Batch 30 skill validation and 3/3 toolkit tests;
- Batch 31 skill validation and 5/5 toolkit tests;
- conservative Batch 31 fake-certification rejection.
