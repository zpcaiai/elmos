from __future__ import annotations

import io
import json
import tempfile
import unittest
import uuid
import zipfile
from pathlib import Path

from scripts.batch30.run_spring_local_supplemental_evidence import (
    EvidenceError,
    prepare_output_directory,
    safe_artifact_inventory,
    write_json,
)


def _nested_jar(group: str, artifact: str, version: str) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            f"META-INF/maven/{group}/{artifact}/pom.properties",
            f"groupId={group}\nartifactId={artifact}\nversion={version}\n",
        )
    return output.getvalue()


class SpringLocalSupplementalTests(unittest.TestCase):
    def test_sbom_inventories_regular_and_war_provided_libraries(self) -> None:
        with tempfile.TemporaryDirectory(prefix="batch30-local-sbom-") as temporary:
            artifact = Path(temporary) / "target.war"
            with zipfile.ZipFile(artifact, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr(
                    "WEB-INF/lib/application-library-1.0.jar",
                    _nested_jar("example", "application-library", "1.0"),
                )
                archive.writestr(
                    "WEB-INF/lib-provided/tomcat-embed-core-10.1.42.jar",
                    _nested_jar("org.apache.tomcat.embed", "tomcat-embed-core", "10.1.42"),
                )
            bom = safe_artifact_inventory(artifact)
            self.assertEqual("CycloneDX", bom["bomFormat"])
            self.assertEqual(2, len(bom["components"]))
            self.assertEqual(
                {"example:application-library:1.0", "org.apache.tomcat.embed:tomcat-embed-core:10.1.42"},
                {component["name"] for component in bom["components"]},
            )
            uuid.UUID(bom["serialNumber"].removeprefix("urn:uuid:"))

    def test_sbom_rejects_unsafe_archive_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="batch30-local-sbom-unsafe-") as temporary:
            artifact = Path(temporary) / "target.war"
            with zipfile.ZipFile(artifact, "w") as archive:
                archive.writestr("../escaped.jar", _nested_jar("x", "y", "1"))
            with self.assertRaisesRegex(EvidenceError, "unsafe archive path"):
                safe_artifact_inventory(artifact)

    def test_sbom_rejects_an_archive_compression_bomb(self) -> None:
        with tempfile.TemporaryDirectory(prefix="batch30-local-sbom-ratio-") as temporary:
            artifact = Path(temporary) / "target.war"
            with zipfile.ZipFile(
                artifact, "w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                archive.writestr("highly-compressible.bin", b"0" * (1024 * 1024))
            with self.assertRaisesRegex(EvidenceError, "compression-ratio budget"):
                safe_artifact_inventory(artifact)

    def test_evidence_json_writer_is_create_only(self) -> None:
        with tempfile.TemporaryDirectory(prefix="batch30-local-json-") as temporary:
            path = Path(temporary) / "evidence.json"
            write_json(path, {"status": "NOT_CERTIFIED"})
            self.assertEqual("NOT_CERTIFIED", json.loads(path.read_text())["status"])
            with self.assertRaisesRegex(EvidenceError, "refusing to overwrite"):
                write_json(path, {"status": "CERTIFIED"})

    def test_output_directory_rejects_a_symlinked_parent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="batch30-local-output-") as temporary:
            root = Path(temporary)
            real_parent = root / "real-parent"
            real_parent.mkdir()
            linked_parent = root / "linked-parent"
            linked_parent.symlink_to(real_parent, target_is_directory=True)
            with self.assertRaisesRegex(EvidenceError, "existing real directory"):
                prepare_output_directory(linked_parent / "supplemental")
            self.assertFalse((real_parent / "supplemental").exists())


if __name__ == "__main__":
    unittest.main()
