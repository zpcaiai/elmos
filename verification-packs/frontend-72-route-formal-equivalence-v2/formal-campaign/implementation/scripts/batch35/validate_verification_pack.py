#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from _common import load

try:
    import jsonschema
except ImportError:
    jsonschema = None


PAIRS = (
    ("pack.json", "verification-pack.schema.json"),
    ("support-matrix.json", "verification-support-matrix.schema.json"),
    ("validation-profile.json", "validation-profile.schema.json"),
    ("oracle-registry.json", "oracle-registry.schema.json"),
    ("properties/sample.json", "property-spec.schema.json"),
    ("metamorphic/sample.json", "metamorphic-relation.schema.json"),
    ("mutation/campaign.json", "mutation-campaign.schema.json"),
    ("fuzz/campaign.json", "fuzz-campaign.schema.json"),
    ("models/model.json", "model-spec.schema.json"),
    ("solver/proof.json", "solver-proof.schema.json"),
    ("counterexamples/sample.json", "counterexample.schema.json"),
    ("assurance/assurance-case.json", "assurance-case.schema.json"),
    ("certification/certification.json", "verification-certification.schema.json"),
)


def main() -> int:
    pack = Path(sys.argv[1])
    schemas = Path(__file__).resolve().parents[2] / "schemas/batch35"
    errors: list[str] = []
    if jsonschema is None:
        errors.append(
            "jsonschema dependency is required; schema validation cannot be skipped"
        )
    for relative, schema_name in PAIRS:
        path = pack / relative
        if not path.is_file():
            errors.append(f"missing {relative}")
            continue
        try:
            data = load(path)
            if jsonschema is not None:
                jsonschema.validate(data, load(schemas / schema_name))
        except Exception as exc:
            errors.append(f"{relative}: {exc}")

    oracle_path = pack / "oracle-registry.json"
    if oracle_path.is_file() and subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("validate_oracle_registry.py")),
            str(oracle_path),
        ],
        check=False,
    ).returncode:
        errors.append("oracle registry validation failed")
    model_path = pack / "models/model.json"
    if model_path.is_file() and subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("validate_model_spec.py")),
            str(model_path),
        ],
        check=False,
    ).returncode:
        errors.append("model spec validation failed")

    manifest = load(pack / "pack.json") if (pack / "pack.json").is_file() else {}
    for key in ("owner", "maintenance_owner"):
        if manifest.get(key) in (None, "", "TODO"):
            errors.append(f"pack {key} is not assigned")
    for key, value in manifest.get("scope", {}).items():
        if isinstance(value, str) and "TODO" in value:
            errors.append(f"scope {key} is placeholder")
    if errors:
        print("\n".join("ERROR: " + item for item in errors), file=sys.stderr)
        return 1
    print(f"OK: verification pack {manifest.get('pack_key')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
