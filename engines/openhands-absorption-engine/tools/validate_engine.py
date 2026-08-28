"""Static integration validator; never executes content from the supplied ZIP."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parents[1]
PACKAGE = REPOSITORY / "skills/subskills/elmos-openhands-absorption-p0-p1-v1.0.0 (1).zip"
EXPECTED_ZIP_SHA256 = "72d151a4d76d3ec4e1e7b7d7401e4c1e390a9ed1a49da19ce4061e45725c3c99"
EXPECTED_COMPONENTS = {
    "models", "artifacts", "ledger", "workspace", "firewall", "tools", "providers", "runtime",
    "gates", "context", "skills", "packages", "dag", "plane", "browser",
}


def main() -> int:
    errors: list[str] = []
    source_digest = hashlib.sha256(PACKAGE.read_bytes()).hexdigest() if PACKAGE.is_file() else ""
    if source_digest != EXPECTED_ZIP_SHA256:
        errors.append("source ZIP digest is absent or changed")
    if not (ROOT / "src/elmos_openhands/__main__.py").is_file():
        errors.append("package entrypoint is missing")
    for component in EXPECTED_COMPONENTS:
        if not (ROOT / f"src/elmos_openhands/{component}.py").is_file():
            errors.append(f"component is missing: {component}")
    for schema in ("execution-event.schema.json", "action-observation.schema.json"):
        try:
            json.loads((ROOT / "src/elmos_openhands/schemas" / schema).read_text())
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"invalid schema {schema}: {error}")
    if PACKAGE.is_file():
        with zipfile.ZipFile(PACKAGE) as archive:
            names = set(archive.namelist())
            if any(name.endswith("/tests/verify-package.py") for name in names):
                # Presence is reported as provenance only. The validator in the
                # archive is deliberately never imported or executed.
                pass
            if len(names) != 50:
                errors.append(f"source ZIP member count changed: {len(names)}")
    result = {"status": "PASS" if not errors else "FAIL", "source_zip_sha256": source_digest, "components": len(EXPECTED_COMPONENTS), "errors": errors}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
