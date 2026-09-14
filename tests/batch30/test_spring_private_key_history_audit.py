import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "spring_private_key_history_audit",
    ROOT / "scripts/batch30/audit_spring_private_key_history.py",
)
assert SPEC is not None and SPEC.loader is not None
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class SpringPrivateKeyHistoryAuditTests(unittest.TestCase):
    def test_detects_only_private_pem_paths_without_reading_contents(self) -> None:
        findings = AUDIT.parse_reachable_objects(
            [
                "a" * 40 + " certification/role-private.pem",
                "b" * 40 + r" framework-packs\route\reviewer-private-key.pem",
                "c" * 40 + " certification/public.pem",
                "d" * 40 + " docs/private-key.txt",
                "e" * 40,
            ]
        )
        self.assertEqual(
            [
                {"object_id": "a" * 40, "path": "certification/role-private.pem"},
                {
                    "object_id": "b" * 40,
                    "path": "framework-packs/route/reviewer-private-key.pem",
                },
            ],
            findings,
        )

    def test_deduplicates_and_canonicalizes_current_tree_paths(self) -> None:
        paths = AUDIT.parse_current_paths(
            [
                r"certification\certifier-private.pem",
                "certification/certifier-private.pem",
                "certification/certifier-public.pem",
            ]
        )
        self.assertEqual(["certification/certifier-private.pem"], paths)


if __name__ == "__main__":
    unittest.main()
