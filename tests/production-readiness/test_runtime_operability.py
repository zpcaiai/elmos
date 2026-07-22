from __future__ import annotations

import copy
import unittest

from tooling.validate_runtime_operability import (
    ROOT,
    validate_prod_database_config,
    validate_repository,
    validate_service_config,
)


class RuntimeOperabilityTests(unittest.TestCase):
    def test_repository_runtime_operability_baseline(self) -> None:
        report = validate_repository(ROOT)
        self.assertEqual("PASS", report["status"], report["errors"])
        self.assertEqual(18, report["service_count"])
        self.assertEqual(18, report["unique_application_names"])
        self.assertEqual(18, report["unique_default_ports"])
        self.assertEqual("NOT_RUN", report["external_evidence_status"])

    def test_missing_readiness_probe_fails_closed(self) -> None:
        valid = {
            "server": {
                "port": "${ELMOS_TEST_PORT:8999}",
                "shutdown": "graceful",
                "error": {
                    "include-message": "never",
                    "include-binding-errors": "never",
                    "include-stacktrace": "never",
                },
            },
            "spring": {
                "application": {"name": "elmos-test"},
                "lifecycle": {"timeout-per-shutdown-phase": "${ELMOS_SHUTDOWN_TIMEOUT:30s}"},
                "mvc": {"problemdetails": {"enabled": True}},
            },
            "management": {
                "endpoint": {
                    "health": {
                        "probes": {"enabled": True, "add-additional-paths": True},
                        "show-details": "never",
                    }
                },
                "endpoints": {"web": {"exposure": {"include": "health,info"}}},
            },
        }
        self.assertEqual([], validate_service_config("test/application.yml", valid))
        invalid = copy.deepcopy(valid)
        invalid["management"]["endpoint"]["health"]["probes"]["enabled"] = False
        self.assertTrue(any("probes.enabled" in error for error in validate_service_config("test", invalid)))

    def test_production_database_credentials_cannot_have_defaults(self) -> None:
        valid = {
            "spring": {
                "config": {"activate": {"on-profile": "prod"}},
                "datasource": {
                    "url": "${ELMOS_DATABASE_URL}",
                    "username": "${ELMOS_DATABASE_USER}",
                    "password": "${ELMOS_DATABASE_PASSWORD}",
                },
            }
        }
        self.assertEqual([], validate_prod_database_config("test", valid))
        invalid = copy.deepcopy(valid)
        invalid["spring"]["datasource"]["password"] = "${ELMOS_DATABASE_PASSWORD:changeme}"
        self.assertTrue(any("REQUIRED_ENV_WITHOUT_DEFAULT" in error for error in validate_prod_database_config("test", invalid)))


if __name__ == "__main__":
    unittest.main()
