import json

from jsonschema import Draft202012Validator

from etgb.io import iter_cases, package_root


def test_smoke_cases_match_schema() -> None:
    root = package_root()
    schema = json.loads((root / "schemas/test-case.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    cases = [c for c in iter_cases(root) if "smoke" in c["profiles"]]
    for case in cases:
        assert list(validator.iter_errors(case)) == []
