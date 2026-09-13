"""Comprehensive test suite for SbomComponentIdentityEngine (Batch 40 - Skill 1379)."""

import unittest

from elmos_mature_platform.sbom_component_identity_engine import SbomComponentIdentityEngine
from elmos_mature_platform.types import (
    ComponentPurlType,
    SbomIdentityRecord,
)


class TestSbomComponentIdentityComprehensive(unittest.TestCase):
    """Rigorous tests covering Package URL resolution, digest attestation, and BOM integrity verification."""

    def setUp(self) -> None:
        self.engine = SbomComponentIdentityEngine()

    def test_register_component_identity_success(self) -> None:
        rec = SbomIdentityRecord(
            identity_id="",
            component_name="spring-boot-starter-web",
            version="3.2.0",
            purl="pkg:maven/org.springframework.boot/spring-boot-starter-web@3.2.0",
            sha256_digest="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            license_expression="Apache-2.0",
            supplier="VMware / Broadcom",
        )
        ident_id = self.engine.register_component_identity(rec)
        self.assertTrue(ident_id.startswith("sbom-id-"))
        self.assertEqual(rec.purl_type, ComponentPurlType.MAVEN)

        retrieved = self.engine.lookup_by_purl(rec.purl)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.component_name, "spring-boot-starter-web")

    def test_register_component_missing_fields(self) -> None:
        rec = SbomIdentityRecord(
            identity_id="",
            component_name="",
            version="",
            purl="",
        )
        with self.assertRaises(ValueError):
            self.engine.register_component_identity(rec)

        rec2 = SbomIdentityRecord(
            identity_id="",
            component_name="express",
            version="4.18.2",
            purl="",
        )
        with self.assertRaises(ValueError):
            self.engine.register_component_identity(rec2)

    def test_purl_type_auto_detection(self) -> None:
        purl_map = {
            "pkg:npm/lodash@4.17.21": ComponentPurlType.NPM,
            "pkg:pypi/requests@2.31.0": ComponentPurlType.PYPI,
            "pkg:golang/github.com/gin-gonic/gin@v1.9.1": ComponentPurlType.GOLANG,
            "pkg:cargo/tokio@1.35.0": ComponentPurlType.CARGO,
            "pkg:nuget/Newtonsoft.Json@13.0.3": ComponentPurlType.NUGET,
        }
        for purl, expected_type in purl_map.items():
            rec = SbomIdentityRecord(
                identity_id="",
                component_name="test-comp",
                version="1.0.0",
                purl=purl,
            )
            self.engine.register_component_identity(rec)
            self.assertEqual(rec.purl_type, expected_type)

    def test_verify_component_digest(self) -> None:
        rec = SbomIdentityRecord(
            identity_id="comp-valid-01",
            component_name="commons-io",
            version="2.14.0",
            purl="pkg:maven/commons-io/commons-io@2.14.0",
            sha256_digest="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        )
        self.engine.register_component_identity(rec)

        # Valid digest match
        valid = self.engine.verify_component_digest(
            "comp-valid-01",
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        )
        self.assertTrue(valid)
        self.assertTrue(rec.verified_identity)
        self.assertFalse(rec.tamper_detected)

        # Tampered digest mismatch
        tampered = self.engine.verify_component_digest(
            "comp-valid-01",
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        )
        self.assertFalse(tampered)
        self.assertFalse(rec.verified_identity)
        self.assertTrue(rec.tamper_detected)

    def test_verify_bom_integrity_batch(self) -> None:
        rec1 = SbomIdentityRecord(
            identity_id="c1",
            component_name="c1",
            version="1.0",
            purl="pkg:npm/c1@1.0",
            sha256_digest="1111",
        )
        rec2 = SbomIdentityRecord(
            identity_id="c2",
            component_name="c2",
            version="1.0",
            purl="pkg:npm/c2@1.0",
            sha256_digest="2222",
        )
        self.engine.register_component_identity(rec1)
        self.engine.register_component_identity(rec2)

        # All pass
        res_pass = self.engine.verify_bom_integrity({"pkg:npm/c1@1.0": "1111", "pkg:npm/c2@1.0": "2222"})
        self.assertEqual(res_pass.verdict, "pass")
        self.assertEqual(res_pass.verified_count, 2)

        # One tampered
        res_fail = self.engine.verify_bom_integrity({"pkg:npm/c1@1.0": "1111", "pkg:npm/c2@1.0": "9999"})
        self.assertEqual(res_fail.verdict, "fail")
        self.assertEqual(res_fail.mismatch_count, 1)
        self.assertIn("pkg:npm/c2@1.0", res_fail.tampered_components)

        # One missing/unresolved
        res_warn = self.engine.verify_bom_integrity({"pkg:npm/c1@1.0": "1111", "pkg:npm/unknown@1.0": "5555"})
        self.assertEqual(res_warn.verdict, "warning")
        self.assertEqual(res_warn.unresolved_count, 1)

    def test_filter_by_license_and_report(self) -> None:
        self.engine.register_component_identity(
            SbomIdentityRecord(
                identity_id="lic-1", component_name="a", version="1", purl="pkg:npm/a@1",
                license_expression="MIT", is_direct_dependency=True
            )
        )
        self.engine.register_component_identity(
            SbomIdentityRecord(
                identity_id="lic-2", component_name="b", version="1", purl="pkg:npm/b@1",
                license_expression="GPL-3.0-only", is_direct_dependency=False
            )
        )

        mit_comps = self.engine.get_components_by_license("MIT")
        self.assertEqual(len(mit_comps), 1)
        self.assertEqual(mit_comps[0].component_name, "a")

        report = self.engine.get_identity_report()
        self.assertEqual(report["total_components"], 2)
        self.assertEqual(report["direct_count"], 1)
        self.assertEqual(report["transitive_count"], 1)


if __name__ == "__main__":
    unittest.main()
