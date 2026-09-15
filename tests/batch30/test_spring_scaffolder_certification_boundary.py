from __future__ import annotations

import ast
from pathlib import Path
from unittest import TestCase, main


ROOT = Path(__file__).resolve().parents[2]
SCAFFOLDERS = (
    ROOT / "scripts" / "batch30" / "scaffold_and_certify_spring_maven_packs.py",
    ROOT / "scripts" / "batch30" / "scaffold_and_certify_spring_boot_4_packs.py",
)


class SpringScaffolderCertificationBoundaryTests(TestCase):
    def test_scaffolders_cannot_generate_or_promote_external_certification(self) -> None:
        for path in SCAFFOLDERS:
            with self.subTest(script=path.name):
                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(path))
                imported_modules = {
                    node.module
                    for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom)
                }
                called_names = {
                    node.func.id
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                }

                self.assertNotIn(
                    "scripts.batch30.execute_spring_certification_campaign",
                    imported_modules,
                )
                self.assertNotIn("execute_campaign", called_names)
                self.assertNotIn("genpkey", source)
                self.assertNotIn(".private.pem", source)
                self.assertNotIn("authorized by Ethan", source)

    def test_scaffolders_require_a_not_certified_gate_result(self) -> None:
        for path in SCAFFOLDERS:
            with self.subTest(script=path.name):
                source = path.read_text(encoding="utf-8")
                self.assertIn("status=experimental decision=NOT_CERTIFIED", source)
                self.assertIn("external execution ``NOT_RUN``", source)
                self.assertNotIn("successfully certified", source.lower())


if __name__ == "__main__":
    main()
