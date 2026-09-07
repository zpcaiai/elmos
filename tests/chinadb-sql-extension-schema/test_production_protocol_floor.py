import ast
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_MODULE = (
    ROOT
    / "engines"
    / "database-data-engine"
    / "sql-transpiler"
    / "src"
    / "elmos_sql_transpiler"
    / "production_qualification.py"
)
REQUEST_SCHEMA = (
    ROOT / "schemas" / "batch31" / "chinadb-production-qualification-request.schema.json"
)
REQUIREMENTS_SCHEMA = (
    ROOT
    / "schemas"
    / "batch31"
    / "chinadb-production-qualification-requirements.schema.json"
)
RESULT_SCHEMA = (
    ROOT / "schemas" / "batch31" / "chinadb-production-qualification-result.schema.json"
)
PROTOCOL_DOCUMENTATION = ROOT / "docs" / "batch31" / "CHINADB_PRODUCTION_QUALIFICATION.md"

ARTIFACT_DIGEST_FIELDS = (
    "sourceSnapshotDigest",
    "sourceCatalogDigest",
    "sourceDataDigest",
    "sourceWorkloadDigest",
    "targetSnapshotDigest",
    "targetReleaseDigest",
    "canonicalIrDigest",
    "transformationDigest",
    "compatibilityRuntimeDigest",
    "runnerDigest",
    "toolchainDigest",
    "developmentCorpusDigest",
    "negativeCorpusDigest",
    "holdoutCorpusDigest",
    "representativeWorkloadDigest",
    "dataFixtureDigest",
    "queryPlanDigest",
    "targetSqlDigest",
    "acceptanceProfileDigest",
    "gateResultDigest",
)

EVIDENCE_DIGEST_FIELDS = (
    "versionProbeDigest",
    "capabilityProbeDigest",
    "renderDigest",
    "targetApplyDigest",
    "introspectionDigest",
    "schemaTypeDigest",
    "queryRoutineDigest",
    "transactionDigest",
    "dataReconciliationDigest",
    "performanceDigest",
    "securityDigest",
    "backupRestoreDigest",
    "cdcDigest",
    "rollbackDigest",
    "cleanupDigest",
    "rawEvidenceDigest",
)

RECEIPT_REFS = {
    "authorization": "#/$defs/nullableAuthorizationEnvelope",
    "execution": "#/$defs/nullableExecutionEnvelope",
    "independentVerification": "#/$defs/nullableVerificationEnvelope",
    "certification": "#/$defs/nullableCertificationEnvelope",
}


def _json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _module_literals():
    tree = ast.parse(PRODUCTION_MODULE.read_text(encoding="utf-8"))
    values = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                try:
                    values[target.id] = ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    continue
    return values


class ChinaDbProductionProtocolFloorTests(unittest.TestCase):
    def test_runtime_protocol_cannot_regress_below_complete_evidence_identity(self):
        values = _module_literals()
        self.assertEqual("1.1.0", values["PROTOCOL_VERSION"])
        self.assertEqual(
            ARTIFACT_DIGEST_FIELDS,
            values["REQUIRED_EXECUTION_ARTIFACT_DIGESTS"],
        )
        self.assertEqual(
            EVIDENCE_DIGEST_FIELDS,
            values["REQUIRED_EXECUTION_EVIDENCE_DIGESTS"],
        )

        source = PRODUCTION_MODULE.read_text(encoding="utf-8")
        self.assertIn("must use one role-specific digest per field", source)
        self.assertIn("artifact and evidence digests must not alias", source)

    def test_schemas_preserve_protocol_floor_and_exact_digest_roles(self):
        request = _json(REQUEST_SCHEMA)
        requirements = _json(REQUIREMENTS_SCHEMA)
        result = _json(RESULT_SCHEMA)

        self.assertEqual("1.1.0", requirements["properties"]["protocolVersion"]["const"])
        self.assertEqual("1.1.0", result["properties"]["protocolVersion"]["const"])

        requirement_target = requirements["properties"]["targets"]["items"]
        self.assertEqual(
            list(ARTIFACT_DIGEST_FIELDS),
            requirement_target["properties"]["requiredArtifactDigests"]["const"],
        )
        self.assertEqual(
            list(EVIDENCE_DIGEST_FIELDS),
            requirement_target["properties"]["requiredEvidenceDigests"]["const"],
        )

        definitions = request["$defs"]
        receipts = definitions["receipts"]["properties"]
        self.assertEqual(
            RECEIPT_REFS,
            {slot: contract["$ref"] for slot, contract in receipts.items()},
        )
        for definition, expected in (
            ("artifactDigests", ARTIFACT_DIGEST_FIELDS),
            ("evidenceDigests", EVIDENCE_DIGEST_FIELDS),
        ):
            digest_contract = definitions[definition]
            self.assertFalse(digest_contract["additionalProperties"])
            self.assertEqual(list(expected), digest_contract["required"])
            self.assertEqual(set(expected), set(digest_contract["properties"]))

        execution_required = set(definitions["executionPayload"]["required"])
        self.assertIn("artifactDigests", execution_required)
        self.assertIn("evidenceDigests", execution_required)
        self.assertNotIn("rawEvidenceDigest", execution_required)
        self.assertNotIn("targetSqlDigest", execution_required)

    def test_operator_documentation_exposes_the_protocol_floor(self):
        documentation = PROTOCOL_DOCUMENTATION.read_text(encoding="utf-8")
        self.assertIn("Protocol `1.1.0`", documentation)
        self.assertIn("role-specific digest sets", documentation)
        self.assertIn("aliased digest roles fail closed", documentation)


if __name__ == "__main__":
    unittest.main()
