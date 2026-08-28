import json
import re
import unittest
from pathlib import Path

import jsonschema


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_ROOT = ROOT / "schemas" / "batch31"
DIGEST = "sha256:" + "a" * 64

TARGETS = (
    ("dm8", "DM8"),
    ("kingbasees", "KingbaseES"),
    ("opengauss", "openGauss"),
    ("tidb", "TiDB"),
    ("gbase-8s", "GBase 8s"),
    ("gbase-8c", "GBase 8c"),
    ("gbase-8a", "GBase 8a"),
    ("highgo-hgdb", "HighGo/HGDB"),
    ("oceanbase-oracle", "OceanBase Oracle"),
    ("oceanbase-mysql", "OceanBase MySQL"),
    ("gaussdb-oracle", "GaussDB Oracle"),
    ("gaussdb-m", "GaussDB M"),
    ("goldendb", "GoldenDB"),
)

SOURCES = (
    ("Oracle", "oracle"),
    ("SQL Server", "sql-server"),
    ("PostgreSQL", "postgresql"),
    ("MySQL/MariaDB", "mysql-mariadb"),
    ("DB2 LUW", "db2-luw"),
    ("Sybase ASE", "sybase-ase"),
)


def load_schema(name):
    return json.loads((SCHEMA_ROOT / name).read_text(encoding="utf-8"))


def commercial_priority(source_slug, target_id):
    if target_id == "gbase-8a":
        return "ANALYTICAL"
    tier_one = {
        "dm8": {"oracle", "sql-server"},
        "kingbasees": {"oracle", "sql-server"},
        "opengauss": {"oracle", "sql-server"},
        "tidb": {"mysql-mariadb"},
        "gbase-8s": {"oracle", "sql-server"},
        "highgo-hgdb": {"oracle", "sql-server"},
        "oceanbase-oracle": {"oracle"},
        "oceanbase-mysql": {"mysql-mariadb"},
        "gaussdb-oracle": {"oracle"},
        "gaussdb-m": {"mysql-mariadb"},
        "goldendb": {"oracle"},
    }
    return "T1" if source_slug in tier_one.get(target_id, set()) else "T2"


def capability_document():
    targets = [
        {
            "id": target_id,
            "label": label,
            "adapterId": f"chinadb.{target_id}.target-adapter.v1",
            "versionRequirement": "exact target version required",
            "compatibilityModeRequirement": "exact compatibility mode required",
            "implementationStatus": "SPEC_ONLY",
            "externalExecution": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }
        for target_id, label in TARGETS
    ]
    routes = [
        {
            "id": f"{source_slug}--to--{target_id}",
            "sourceFamily": source_family,
            "targetId": target_id,
            "priority": commercial_priority(source_slug, target_id),
            "state": "SPEC_ONLY",
            "externalExecution": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }
        for target_id, _ in TARGETS
        for source_family, source_slug in SOURCES
    ]
    return {
        "schemaVersion": "1.0",
        "package": "chinadb-commercial-migration-skills",
        "version": "1.0.0",
        "capabilitySnapshotDigest": DIGEST,
        "targetCount": 13,
        "plannedRouteCount": 78,
        "targets": targets,
        "plannedRoutes": routes,
        "excludedTargets": [
            {"id": "polardb", "label": "PolarDB", "reason": "Excluded by package scope."},
            {"id": "polardb-x", "label": "PolarDB-X", "reason": "Excluded by package scope."},
            {"id": "tdsql", "label": "TDSQL", "reason": "Excluded by package scope."},
        ],
        "implementationStatus": "SPEC_ONLY",
        "externalExecution": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "boundaries": {
            "exactCommercialTargetProfilesRegistered": False,
            "verifiedTargetRenderers": 0,
            "productionDatabaseAccess": False,
            "targetSqlMayBeEmitted": False,
            "claim": "Planning inventory only; target adapters and target execution are not implemented.",
        },
    }


def preflight_request():
    return {
        "schemaVersion": "1.0",
        "queryId": "customer-orders-by-id",
        "sourceProfile": "oracle-26ai-ee",
        "targetId": "dm8",
        "targetVersion": "8.1.3.140",
        "targetEdition": "enterprise",
        "compatibilityMode": "oracle",
        "targetDriver": "dm-jdbc-8.1.3.140",
        "targetCharset": "UTF-8",
        "targetCollation": "BINARY",
        "targetTimeZone": "Asia/Shanghai",
        "capabilitySnapshotDigest": DIGEST,
        "sql": "SELECT order_id FROM orders WHERE customer_id = :customer_id",
        "parameters": [
            {"name": "customer_id", "logicalType": "DECIMAL(20,0)", "nullable": False}
        ],
    }


def preflight_result():
    return {
        "schemaVersion": "1.0",
        "queryId": "customer-orders-by-id",
        "sourceProfile": "oracle-26ai-ee",
        "target": {
            "id": "dm8",
            "label": "DM8",
            "version": "8.1.3.140",
            "edition": "enterprise",
            "compatibilityMode": "oracle",
            "driver": "dm-jdbc-8.1.3.140",
            "charset": "UTF-8",
            "collation": "BINARY",
            "timeZone": "Asia/Shanghai",
            "adapterId": "chinadb.dm8.target-adapter.v1",
            "implementationStatus": "SPEC_ONLY",
        },
        "routeId": "oracle--to--dm8",
        "state": "BLOCKED",
        "sourceDigest": DIGEST,
        "capabilitySnapshotDigest": DIGEST,
        "statements": [
            {
                "index": 0,
                "kind": "SELECT",
                "sourceAst": [{"c": "sqlglot.expressions.Select"}],
                "obligations": ["RESULT_ORDER_UNDEFINED"],
            }
        ],
        "blockers": [
            {
                "code": "TARGET_ADAPTER_NOT_IMPLEMENTED",
                "severity": "ERROR",
                "statementIndex": 0,
                "message": "No verified renderer is registered for this exact target tuple.",
            }
        ],
        "targetSql": None,
        "verification": {
            "sourceParse": "PASSED",
            "targetAdapter": "NOT_RUN",
            "targetEmit": "NOT_RUN",
            "targetReparse": "NOT_RUN",
            "sourceExecution": "NOT_RUN",
            "targetExecution": "NOT_RUN",
            "resultEquivalence": "NOT_RUN",
            "externalExecution": "NOT_RUN",
        },
        "certification": "NOT_CERTIFIED",
    }


def skill_ids():
    status_path = (
        ROOT
        / "skills"
        / "chinadb-commercial-migration-skills-v1.0.0"
        / "IMPLEMENTATION_STATUS.json"
    )
    return sorted(json.loads(status_path.read_text(encoding="utf-8")))


def skill_capability_document():
    bindings = [
        {
            "skillId": skill_id,
            "alias": f"chinadb-{skill_id}",
            "handlerId": f"handler:{skill_id}",
            "category": "bounded-local",
            "dependencies": [],
            "externalEffects": [],
            "localCodeStatus": "CODE_IMPLEMENTED",
            "externalExecution": "NOT_RUN",
            "independentVerification": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }
        for skill_id in skill_ids()
    ]
    return {
        "schemaVersion": "1.0",
        "package": "chinadb-commercial-migration-skills",
        "runtimeVersion": "1.0.0",
        "skillCount": 47,
        "codeImplementedCount": 47,
        "boundedLocalHandlerCoverage": {
            "implemented": 47,
            "total": 47,
            "rate": 1.0,
        },
        "importedSpecificationStatus": "SPEC_ONLY",
        "productionDefinitionOfDoneCount": 0,
        "productionDefinitionOfDone": "BLOCKED_EXTERNAL_EVIDENCE",
        "bindings": bindings,
        "bindingDigest": DIGEST,
        "externalExecution": "NOT_RUN",
        "independentVerification": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "claim": "Repository-owned bounded local handlers; external execution is not run.",
    }


def skill_request():
    return {
        "scope": {
            "tenantId": "tenant-1",
            "projectId": "project-1",
            "actorId": "actor-1",
        },
        "objects": [],
    }


def skill_result():
    return {
        "schemaVersion": "1.0",
        "package": "chinadb-commercial-migration-skills",
        "runtimeVersion": "1.0.0",
        "skillId": "01-estate-inventory-assessment",
        "alias": "chinadb-01-estate-inventory-assessment",
        "handlerId": "inventory",
        "scope": skill_request()["scope"],
        "state": "LOCAL_COMPLETED",
        "localCodeStatus": "CODE_IMPLEMENTED",
        "requestDigest": DIGEST,
        "artifactDigest": DIGEST,
        "artifacts": {},
        "checks": [],
        "blockers": [],
        "effects": {
            "declaredExternalEffects": [],
            "externalEffectsExecuted": [],
        },
        "verification": {
            "localHandler": "PASSED",
            "externalExecution": "NOT_RUN",
            "independentVerification": "NOT_RUN",
        },
        "certification": "NOT_CERTIFIED",
        "resultDigest": DIGEST,
    }


def production_request():
    return {
        "schemaVersion": "1.0",
        "scope": {
            "tenantId": "tenant-1",
            "projectId": "project-1",
            "actorId": "actor-1",
        },
        "capabilitySnapshotDigest": DIGEST,
        "trustStoreDigest": None,
        "implementer": {
            "actorId": "actor-1",
            "organizationId": "elmos-engineering",
        },
        "targets": [
            {
                "targetId": target_id,
                "exactTuple": None,
                "disposableEnvironment": None,
                "vendorTools": [],
                "independentVerifier": None,
                "receipts": {
                    "authorization": None,
                    "execution": None,
                    "independentVerification": None,
                    "certification": None,
                },
            }
            for target_id, _ in TARGETS
        ],
    }


def exact_tuple():
    return {
        "productId": "dm8",
        "productVersion": "8.1.3.140",
        "edition": "enterprise-exact",
        "compatibilityMode": "native-explicit",
        "deploymentTopology": "single-node-disposable",
        "provider": "vendor-dm8",
        "serviceTier": "licensed-sandbox",
        "region": "cn-test-1",
        "driver": {
            "name": "dm-jdbc",
            "version": "8.1.3.140",
            "artifactDigest": DIGEST,
        },
        "charset": "UTF-8",
        "collation": "BINARY-EXACT",
        "timeZone": "Asia/Shanghai",
        "timeZoneDataVersion": "2026b",
        "sqlMode": "native-default-explicit",
        "extensions": [],
        "runtimeArtifactDigest": DIGEST,
    }


def production_requirements():
    operations = [
        "APPLY_SANDBOX",
        "BACKUP_RESTORE",
        "CAPABILITY_PROBE",
        "CAPTURE_PLAN",
        "CDC_RECONCILIATION",
        "CLEANUP",
        "EXECUTE_WORKLOAD",
        "INTROSPECT",
        "RENDER",
        "VERSION_PROBE",
    ]
    return {
        "schemaVersion": "1.0",
        "protocolVersion": "1.0.0",
        "package": "chinadb-commercial-migration-skills",
        "capabilitySnapshotDigest": DIGEST,
        "targetCount": 13,
        "targets": [
            {
                "targetId": target_id,
                "label": label,
                "adapterId": f"chinadb.{target_id}.target-adapter.v1",
                "requiredOperations": operations,
                "requiredEvidenceChain": [
                    "environment-authorization",
                    "external-target-execution",
                    "independent-verification",
                    "certification-decision",
                ],
                "currentState": "BLOCKED_EXTERNAL_INPUT",
            }
            for target_id, label in TARGETS
        ],
        "trust": {
            "domain": "elmos.chinadb.production-qualification.v1",
            "algorithm": "ed25519",
            "requiredRoles": [
                "certification-authority",
                "environment-authorizer",
                "external-target-executor",
                "independent-verifier",
            ],
            "operatorPinnedTrustStoreRequired": True,
        },
        "productionBoundaries": {
            "externalExecution": "NOT_RUN",
            "independentVerification": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
            "targetSql": None,
            "productionDefinitionOfDoneCount": 0,
        },
        "requirementsDigest": DIGEST,
    }


def production_result():
    return {
        "schemaVersion": "1.0",
        "protocolVersion": "1.0.0",
        "package": "chinadb-commercial-migration-skills",
        "scope": production_request()["scope"],
        "scopeDigest": DIGEST,
        "capabilitySnapshotDigest": DIGEST,
        "trustStoreDigest": None,
        "requestDigest": DIGEST,
        "evaluatedAt": "2026-08-28T12:00:00Z",
        "targets": [
            {
                "targetId": target_id,
                "label": label,
                "adapterId": f"chinadb.{target_id}.target-adapter.v1",
                "state": "BLOCKED_INPUT",
                "qualificationInputDigest": None,
                "exactTupleDigest": None,
                "environmentDigest": None,
                "vendorToolDigests": [],
                "authorization": "NOT_RUN",
                "externalExecution": "NOT_RUN",
                "independentVerification": "NOT_RUN",
                "certification": "NOT_CERTIFIED",
                "targetSql": None,
                "evidenceEnvelopeDigests": [],
                "blockers": [
                    {
                        "code": "EXACT_TARGET_TUPLE_REQUIRED",
                        "severity": "ERROR",
                        "message": f"{target_id} is missing exactTuple.",
                    }
                ],
            }
            for target_id, label in TARGETS
        ],
        "summary": {
            "targetCount": 13,
            "inputCompleteTargetCount": 0,
            "authorizationVerifiedTargetCount": 0,
            "externalExecutionPassedTargetCount": 0,
            "independentlyVerifiedTargetCount": 0,
            "productionDefinitionOfDoneCount": 0,
        },
        "externalExecution": "NOT_RUN",
        "independentVerification": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "targetSql": None,
        "productionDefinitionOfDoneCount": 0,
        "effects": {"externalCallsExecuted": []},
        "resultDigest": DIGEST,
    }


def production_trust_store():
    return {
        "schemaVersion": "1.0",
        "trustDomain": "elmos.chinadb.production-qualification.v1",
        "keys": [
            {
                "keyId": "authorizer-key-1",
                "role": "environment-authorizer",
                "actorId": "customer-owner",
                "organizationId": "customer-org",
                "publicKey": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
                "notBefore": "2026-01-01T00:00:00Z",
                "notAfter": "2027-01-01T00:00:00Z",
                "revoked": False,
            }
        ],
    }


class ChinaDbSqlExtensionSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.capability_schema = load_schema("chinadb-commercial-capabilities.schema.json")
        cls.request_schema = load_schema("chinadb-sql-preflight-request.schema.json")
        cls.result_schema = load_schema("chinadb-sql-preflight-result.schema.json")
        cls.skill_capability_schema = load_schema("chinadb-skill-capabilities.schema.json")
        cls.skill_request_schema = load_schema("chinadb-skill-request.schema.json")
        cls.skill_result_schema = load_schema("chinadb-skill-result.schema.json")
        cls.production_request_schema = load_schema(
            "chinadb-production-qualification-request.schema.json"
        )
        cls.production_result_schema = load_schema(
            "chinadb-production-qualification-result.schema.json"
        )
        cls.production_requirements_schema = load_schema(
            "chinadb-production-qualification-requirements.schema.json"
        )
        cls.production_trust_schema = load_schema(
            "chinadb-production-trust-store.schema.json"
        )
        cls.capability_validator = jsonschema.Draft202012Validator(cls.capability_schema)
        cls.request_validator = jsonschema.Draft202012Validator(cls.request_schema)
        cls.result_validator = jsonschema.Draft202012Validator(cls.result_schema)
        cls.skill_capability_validator = jsonschema.Draft202012Validator(
            cls.skill_capability_schema
        )
        cls.skill_request_validator = jsonschema.Draft202012Validator(cls.skill_request_schema)
        cls.skill_result_validator = jsonschema.Draft202012Validator(cls.skill_result_schema)
        cls.production_request_validator = jsonschema.Draft202012Validator(
            cls.production_request_schema
        )
        cls.production_result_validator = jsonschema.Draft202012Validator(
            cls.production_result_schema
        )
        cls.production_requirements_validator = jsonschema.Draft202012Validator(
            cls.production_requirements_schema
        )
        cls.production_trust_validator = jsonschema.Draft202012Validator(
            cls.production_trust_schema
        )

    def assertValid(self, validator, instance):
        errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.path))
        self.assertEqual([], errors, "\n".join(error.message for error in errors))

    def assertInvalid(self, validator, instance):
        self.assertTrue(list(validator.iter_errors(instance)), "instance unexpectedly validated")

    def test_schemas_are_valid_draft_2020_12(self):
        for schema in (
            self.capability_schema,
            self.request_schema,
            self.result_schema,
            self.skill_capability_schema,
            self.skill_request_schema,
            self.skill_result_schema,
            self.production_request_schema,
            self.production_result_schema,
            self.production_requirements_schema,
            self.production_trust_schema,
        ):
            jsonschema.Draft202012Validator.check_schema(schema)

    def test_production_qualification_schemas_preserve_exact_13_target_boundary(self):
        self.assertValid(self.production_request_validator, production_request())
        checked_in_draft = json.loads(
            (
                ROOT
                / "engines"
                / "database-data-engine"
                / "sql-transpiler"
                / "examples"
                / "chinadb-production-qualification-draft.json"
            ).read_text(encoding="utf-8")
        )
        self.assertValid(self.production_request_validator, checked_in_draft)
        self.assertValid(self.production_result_validator, production_result())
        self.assertValid(
            self.production_requirements_validator,
            production_requirements(),
        )
        self.assertValid(self.production_trust_validator, production_trust_store())

        missing_target = production_request()
        missing_target["targets"].pop()
        self.assertInvalid(self.production_request_validator, missing_target)

        floating = production_request()
        floating["targets"][0]["exactTuple"] = exact_tuple()
        floating["targets"][0]["exactTuple"]["productVersion"] = "latest"
        self.assertInvalid(self.production_request_validator, floating)

        production_write = production_request()
        production_write["targets"][0]["disposableEnvironment"] = {
            "environmentId": "sandbox-dm8",
            "kind": "DISPOSABLE_INSTANCE",
            "endpointRef": "endpoint-ref-dm8",
            "credentialRef": "credential-ref-dm8",
            "providerResourceRef": "resource-ref-dm8",
            "dataProfile": "SYNTHETIC",
            "productionData": True,
            "writeScope": "DISPOSABLE_ONLY",
            "expiresAt": "2026-10-01T00:00:00Z",
            "cleanupDeadline": "2026-10-02T00:00:00Z",
        }
        self.assertInvalid(self.production_request_validator, production_write)

        leaked_sql = production_result()
        leaked_sql["targetSql"] = "SELECT 1"
        self.assertInvalid(self.production_result_validator, leaked_sql)

        fabricated_effect = production_result()
        fabricated_effect["effects"]["externalCallsExecuted"] = ["target-write"]
        self.assertInvalid(self.production_result_validator, fabricated_effect)

    def test_skill_runtime_schemas_preserve_exact_local_and_external_boundaries(self):
        self.assertEqual(47, len(skill_ids()))
        self.assertValid(self.skill_capability_validator, skill_capability_document())
        self.assertValid(self.skill_request_validator, skill_request())
        self.assertValid(self.skill_result_validator, skill_result())

        missing_scope = skill_request()
        missing_scope.pop("scope")
        self.assertInvalid(self.skill_request_validator, missing_scope)

        false_external_claim = skill_result()
        false_external_claim["verification"]["externalExecution"] = "PASSED"
        self.assertInvalid(self.skill_result_validator, false_external_claim)

        fabricated_effect = skill_result()
        fabricated_effect["effects"]["externalEffectsExecuted"] = ["target-write"]
        self.assertInvalid(self.skill_result_validator, fabricated_effect)

    def test_capability_snapshot_accepts_exact_planning_boundary(self):
        document = capability_document()
        self.assertEqual(13, len(document["targets"]))
        self.assertEqual(78, len(document["plannedRoutes"]))
        self.assertValid(self.capability_validator, document)

    def test_capability_snapshot_rejects_missing_target_or_route(self):
        missing_target = capability_document()
        missing_target["targets"].pop()
        self.assertInvalid(self.capability_validator, missing_target)

        missing_route = capability_document()
        missing_route["plannedRoutes"].pop()
        self.assertInvalid(self.capability_validator, missing_route)

    def test_capability_snapshot_rejects_runtime_or_certification_claims(self):
        for field, false_claim in (
            ("implementationStatus", "IMPLEMENTED"),
            ("externalExecution", "PASSED"),
            ("certification", "CERTIFIED"),
        ):
            document = capability_document()
            document[field] = false_claim
            self.assertInvalid(self.capability_validator, document)

        document = capability_document()
        document["targets"][0]["externalExecution"] = "PASSED"
        self.assertInvalid(self.capability_validator, document)

    def test_preflight_request_accepts_existing_exact_source_profile(self):
        self.assertValid(self.request_validator, preflight_request())

    def test_preflight_request_rejects_invented_source_or_mutable_target(self):
        request = preflight_request()
        request["sourceProfile"] = "db2-latest"
        self.assertInvalid(self.request_validator, request)

        request = preflight_request()
        request["targetVersion"] = "latest"
        self.assertInvalid(self.request_validator, request)

        request = preflight_request()
        request["targetDriver"] = "unknown"
        self.assertInvalid(self.request_validator, request)

    def test_preflight_request_requires_complete_exact_target_tuple(self):
        for field in (
            "targetEdition",
            "targetDriver",
            "targetCharset",
            "targetCollation",
            "targetTimeZone",
        ):
            request = preflight_request()
            request.pop(field)
            self.assertInvalid(self.request_validator, request)

    def test_preflight_contract_rejects_bare_floating_tuple_tokens(self):
        request = preflight_request()
        request["targetVersion"] = "x"
        self.assertInvalid(self.request_validator, request)

        request = preflight_request()
        request["targetDriver"] = "X"
        self.assertInvalid(self.request_validator, request)

        result = preflight_result()
        result["target"]["version"] = "X"
        self.assertInvalid(self.result_validator, result)

        result = preflight_result()
        result["target"]["edition"] = "x"
        self.assertInvalid(self.result_validator, result)

    def test_preflight_request_requires_snapshot_and_typed_parameters(self):
        request = preflight_request()
        request.pop("capabilitySnapshotDigest")
        self.assertInvalid(self.request_validator, request)

        request = preflight_request()
        request["parameters"][0].pop("nullable")
        self.assertInvalid(self.request_validator, request)

    def test_blocked_preflight_result_accepts_object_or_array_source_ast(self):
        result = preflight_result()
        self.assertValid(self.result_validator, result)

        result["statements"][0]["sourceAst"] = {"type": "Select", "expressions": []}
        self.assertValid(self.result_validator, result)

    def test_blocked_preflight_result_requires_explicit_null_target_sql(self):
        result = preflight_result()
        result.pop("targetSql")
        self.assertInvalid(self.result_validator, result)

    def test_source_parse_failure_is_a_typed_blocked_result(self):
        result = preflight_result()
        result["statements"] = []
        result["blockers"] = [
            {
                "code": "SOURCE_PARSE_FAILED",
                "severity": "ERROR",
                "statementIndex": None,
                "message": "The exact source profile parser rejected the SQL.",
            }
        ]
        result["verification"]["sourceParse"] = "FAILED"
        self.assertValid(self.result_validator, result)

        result["verification"]["sourceParse"] = "PASSED"
        self.assertInvalid(self.result_validator, result)

    def test_preflight_result_rejects_generated_target_sql_or_ready_state(self):
        result = preflight_result()
        result["targetSql"] = "SELECT order_id FROM orders"
        self.assertInvalid(self.result_validator, result)

        result = preflight_result()
        result["state"] = "SYNTAX_READY"
        self.assertInvalid(self.result_validator, result)

    def test_preflight_result_rejects_untyped_statement_or_missing_blocker(self):
        result = preflight_result()
        result["statements"][0]["sourceAst"] = "SELECT ..."
        self.assertInvalid(self.result_validator, result)

        result = preflight_result()
        result["blockers"] = []
        self.assertInvalid(self.result_validator, result)

    def test_preflight_result_rejects_fabricated_execution_or_certification(self):
        result = preflight_result()
        result["verification"]["targetExecution"] = "PASSED"
        self.assertInvalid(self.result_validator, result)

        result = preflight_result()
        result["certification"] = "CERTIFIED"
        self.assertInvalid(self.result_validator, result)

    def test_java_worker_and_control_plane_protocols_do_not_drift(self):
        worker_path = ROOT / "engines" / "database-data-engine" / "src" / "main" / "java" / "io" / "elmos" / "databasedata" / "ChinaDbSqlPreflightProtocol.java"
        control_path = ROOT / "apps" / "control-plane" / "src" / "main" / "java" / "io" / "elmos" / "controlplane" / "ChinaDbSqlPreflightProtocol.java"
        worker = worker_path.read_text(encoding="utf-8")
        control = control_path.read_text(encoding="utf-8")

        def normalize(source):
            source = re.sub(r"package io\.elmos\.[a-z]+;", "package io.elmos.shared;", source)
            source = source.replace("io.elmos.databasedata.", "io.elmos.shared.")
            source = source.replace("io.elmos.controlplane.", "io.elmos.shared.")
            source = source.replace("sidecar hop", "upstream hop")
            source = source.replace("worker hop", "upstream hop")
            return source

        self.assertEqual(normalize(worker), normalize(control))
        constants = dict(re.findall(
            r"static final int (MAX_[A-Z_]+) = ([^;]+);",
            worker,
        ))
        self.assertEqual(constants, dict(re.findall(
            r"static final int (MAX_[A-Z_]+) = ([^;]+);",
            control,
        )))
        self.assertEqual("1_310_720", constants["MAX_REQUEST_BYTES"])
        self.assertEqual("256 * 1024", constants["MAX_SQL_BYTES"])
        self.assertEqual("4_194_304", constants["MAX_RESPONSE_BYTES"])


if __name__ == "__main__":
    unittest.main()
