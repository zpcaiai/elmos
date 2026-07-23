from __future__ import annotations

import copy
import unittest

from tooling.validate_runtime_operability import (
    ROOT,
    validate_prod_database_config,
    validate_repository,
    validate_service_config,
    validate_compose_web_routing,
    validate_exception_handler_source,
)


class RuntimeOperabilityTests(unittest.TestCase):
    def test_repository_runtime_operability_baseline(self) -> None:
        report = validate_repository(ROOT)
        self.assertEqual("PASS", report["status"], report["errors"])
        self.assertEqual(18, report["service_count"])
        self.assertEqual(18, report["unique_application_names"])
        self.assertEqual(18, report["unique_default_ports"])
        self.assertGreaterEqual(report["compose_service_count"], 20)
        self.assertTrue(report["checks"]["web_control_plane_routing"])
        self.assertTrue(report["checks"]["safe_error_responses"])
        self.assertGreaterEqual(report["explicit_exception_handler_files"], 20)
        self.assertEqual("NOT_RUN", report["external_evidence_status"])

    def test_explicit_exception_messages_cannot_bypass_safe_server_config(self) -> None:
        unsafe = """
        @ExceptionHandler(IllegalArgumentException.class)
        Map<String,Object> bad(IllegalArgumentException error) {
            return Map.of("message", error.getMessage());
        }
        """
        errors = validate_exception_handler_source("UnsafeController.java", unsafe)
        self.assertTrue(any("EXPLICIT_EXCEPTION_MESSAGE_DISCLOSURE" in error for error in errors))
        safe = unsafe.replace('error.getMessage()', '"The request was rejected."')
        self.assertEqual([], validate_exception_handler_source("SafeController.java", safe))

    def test_web_console_uses_compose_service_discovery(self) -> None:
        valid = {
            "services": {
                "control-plane": {},
                "web-console": {
                    "environment": {"CONTROL_PLANE_BASE_URL": "http://control-plane:8080"},
                    "depends_on": ["control-plane"],
                },
            }
        }
        self.assertEqual([], validate_compose_web_routing("compose.yml", valid))

    def test_web_console_loopback_backend_fails_closed(self) -> None:
        invalid = {
            "services": {
                "control-plane": {},
                "web-console": {
                    "environment": {"CONTROL_PLANE_BASE_URL": "http://127.0.0.1:8080"},
                    "depends_on": ["control-plane"],
                },
            }
        }
        errors = validate_compose_web_routing("compose.yml", invalid)
        self.assertTrue(any("LOOPBACK_BACKEND_FORBIDDEN" in error for error in errors))

    def test_web_console_missing_dependency_fails_closed(self) -> None:
        invalid = {
            "services": {
                "control-plane": {},
                "web-console": {
                    "environment": {"CONTROL_PLANE_BASE_URL": "http://control-plane:8080"},
                },
            }
        }
        errors = validate_compose_web_routing("compose.yml", invalid)
        self.assertTrue(any("depends_on" in error for error in errors))

    def test_web_console_unknown_backend_service_fails_closed(self) -> None:
        invalid = {
            "services": {
                "control-plane": {},
                "web-console": {
                    "environment": {"CONTROL_PLANE_BASE_URL": "http://missing-control-plane:8080"},
                    "depends_on": ["control-plane"],
                },
            }
        }
        errors = validate_compose_web_routing("compose.yml", invalid)
        self.assertTrue(any("UNKNOWN_BACKEND_SERVICE" in error for error in errors))

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
