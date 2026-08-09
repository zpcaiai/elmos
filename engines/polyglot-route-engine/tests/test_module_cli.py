from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from elmos_polyglot_route import cli


def test_module_subcommand_routes_the_exact_manifest_to_the_module_engine(
    tmp_path: Path,
    monkeypatch: Any,
    capsys: Any,
) -> None:
    source = tmp_path / "equivalence_module.cpp"
    manifest = tmp_path / "cases.json"
    output = tmp_path / "evidence"
    source.write_text("// fixture\n", encoding="utf-8")
    manifest.write_text("{}\n", encoding="utf-8")
    observed: dict[str, Any] = {}

    def fake_migrate_module(
        source_path: Path,
        source_language: str,
        target_language: str,
        manifest_path: Path,
        output_path: Path,
    ) -> dict[str, Any]:
        observed.update(
            {
                "source": source_path,
                "source_language": source_language,
                "target_language": target_language,
                "manifest": manifest_path,
                "output": output_path,
            }
        )
        return {
            "profile": "typed-pure-module-v1",
            "status": "PASSED",
            "certification_status": "NOT_CERTIFIED",
        }

    monkeypatch.setattr(cli, "migrate_module", fake_migrate_module)
    status = cli.main(
        [
            "module",
            "--source",
            str(source),
            "--source-language",
            "cpp",
            "--target-language",
            "swift",
            "--manifest",
            str(manifest),
            "--output",
            str(output),
        ]
    )

    assert status == 0
    assert observed == {
        "source": source,
        "source_language": "cpp",
        "target_language": "swift",
        "manifest": manifest,
        "output": output,
    }
    response = json.loads(capsys.readouterr().out)
    assert response["profile"] == "typed-pure-module-v1"
    assert response["status"] == "PASSED"
    assert response["certification_status"] == "NOT_CERTIFIED"
