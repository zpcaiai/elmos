"""Fail-closed catalog-to-Pack referential and capability status controls."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "scripts/operations/validate_spring_route_contract.py"
spec = importlib.util.spec_from_file_location("spring_catalog_pack_refs", VALIDATOR)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class SpringCatalogPackReferencesTests(unittest.TestCase):
    def test_repository_catalog_references_resolve_without_certification(self) -> None:
        routes = module.parse_catalog()
        module.check_pack_references(routes)
        self.assertEqual(
            {str(route["pack_key"]) for route in routes} & module.INVENTORY_PACK_KEYS,
            module.INVENTORY_PACK_KEYS,
        )
        for key in module.INVENTORY_PACK_KEYS:
            pack = ROOT / "framework-packs" / key
            self.assertEqual(json.loads((pack / "pack.json").read_text())["status"], "research")
            self.assertEqual(
                json.loads((pack / "certification/certification.json").read_text())
                ["certification_decision"], "NOT_CERTIFIED"
            )

    def test_missing_or_unsafe_pack_reference_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            for key, reason in (
                ("missing-pack", "ROUTE_PACK_MISSING"),
                ("../other", "ROUTE_PACK_KEY_UNSAFE"),
            ):
                with self.subTest(key=key):
                    with self.assertRaisesRegex(module.ContractError, reason):
                        module.check_pack_references(
                            [{"route_id": "route-a", "pack_key": key}], repo
                        )

    def test_inventory_pack_cannot_self_certify_or_promote_capabilities(self) -> None:
        key = "spring-boot-2-7-to-3-2-12"
        with tempfile.TemporaryDirectory() as temporary:
            pack = Path(temporary) / "framework-packs" / key
            (pack / "certification").mkdir(parents=True)
            (pack / "pack.json").write_text(json.dumps({"pack_key": key, "status": "research"}))
            certificate = {"status": "research", "certification_decision": "CERTIFIED"}
            (pack / "certification/certification.json").write_text(json.dumps(certificate))
            (pack / "support-matrix.json").write_text(
                json.dumps({"capabilities": [{"status": "experimental"}]})
            )
            route = [{"route_id": "route-a", "pack_key": key}]
            with self.assertRaisesRegex(module.ContractError, "INVENTORY_PACK_CANNOT_SELF_CERTIFY"):
                module.check_pack_references(route, Path(temporary))
            certificate["certification_decision"] = "NOT_CERTIFIED"
            (pack / "certification/certification.json").write_text(json.dumps(certificate))
            (pack / "support-matrix.json").write_text(
                json.dumps({"capabilities": [{"status": "supported"}]})
            )
            with self.assertRaisesRegex(module.ContractError, "INVENTORY_PACK_CANNOT_PROMOTE"):
                module.check_pack_references(route, Path(temporary))
