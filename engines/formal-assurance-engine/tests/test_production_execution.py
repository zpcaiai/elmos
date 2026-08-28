from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import threading
import unittest
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

from elmos_formal_assurance.artifact_store import ContentAddressedArtifactStore
from elmos_formal_assurance.canonical import digest_bytes, digest_value
from elmos_formal_assurance.contracts import (
    AssuranceLevel,
    ProofStatus,
    Scope,
    SkillOutcome,
    TrustedIdentity,
)
from elmos_formal_assurance.database import SQLiteDifferentialExecutor
from elmos_formal_assurance.execution import (
    ADAPTERS,
    ExecutionAuthorizationError,
    ExecutionContractError,
    ExecutionFile,
    ExecutionPermit,
    ExecutionPermitSigner,
    ExecutionState,
    NativeExecutionReceipt,
    NativeExecutionRequest,
    ProcessExecutionResult,
    ResourceLimits,
    SandboxKind,
    ToolchainRegistration,
    execution_binding_digest,
    interpret_tool_result,
)
from elmos_formal_assurance.observability import (
    FormalObservabilityService,
    OtlpHttpJsonExporter,
)
from elmos_formal_assurance.production import ProductionSkillExecutor
from elmos_formal_assurance.runtime import FormalAssuranceRuntime, RuntimeConfig
from elmos_formal_assurance.store import StateStore, StoreError


SOURCE_ADAPTERS = {
    "alive2",
    "alloy",
    "apalache",
    "boogie",
    "cvc5",
    "dafny",
    "frama-c",
    "jpf",
    "k-framework",
    "kani",
    "key",
    "lean",
    "openjml",
    "sqlsolver",
    "tlc",
    "verieql",
    "z3",
}


def current_scope(tenant: str = "tenant-a") -> Scope:
    return Scope(
        tenant,
        "account-a",
        "project-a",
        "a" * 64,
        "b" * 64,
        "c" * 64,
        "production-test",
    )


def executable_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def local_outcome(skill_id: str = "elmos-data-invariant-verifier") -> SkillOutcome:
    return SkillOutcome(
        skill_id=skill_id,
        handler_id="execute_" + skill_id.replace("-", "_"),
        implementation_state="PRODUCTION_CODE_COMPLETE",
        capability_state="CODE_COMPLETE_NATIVE_EVIDENCE_REQUIRED",
        proof_status=ProofStatus.BOUNDED_NO_COUNTEREXAMPLE,
        assurance_level=AssuranceLevel.A1_BOUNDED,
        mode="BOUNDED",
        output={"bounded": True},
    )


class ProductionExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = StateStore()
        self.signer = ExecutionPermitSigner(b"formal-production-test-key-000001")
        self.scope = current_scope()
        self.identity = TrustedIdentity(
            "tenant-a",
            "operator-a",
            "project-a",
            ("formal-assurance:execute",),
        )

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def execution_payload(
        self,
        *,
        skill_id: str,
        subject_id: str,
        adapter_id: str,
        files: dict[str, object],
        semantics: str,
        options: dict[str, object] | None = None,
        permit_id: str = "permit-a",
        nonce: str = "nonce-a",
    ) -> dict[str, object]:
        value: dict[str, object] = {
            "adapterId": adapter_id,
            "files": files,
            "options": options or {},
            "querySemantics": semantics,
            "timeoutSeconds": 10,
        }
        binding = execution_binding_digest(
            self.scope, skill_id, subject_id, value
        )
        value["permit"] = self.signer.issue(
            permit_id=permit_id,
            nonce=nonce,
            scope=self.scope,
            skill_id=skill_id,
            subject_id=subject_id,
            adapter_id=adapter_id,
            execution_digest=binding,
        ).to_dict()
        return value

    def test_all_seventeen_declared_verifier_adapters_have_repository_owned_definitions(self) -> None:
        self.assertTrue(SOURCE_ADAPTERS.issubset(ADAPTERS))
        for adapter_id in SOURCE_ADAPTERS:
            definition = ADAPTERS[adapter_id]
            self.assertTrue(definition.required_files)
            self.assertTrue(definition.argv)
            self.assertNotEqual(definition.parser, "exit-code-only")

    @unittest.skipUnless(shutil.which("z3"), "z3 is not installed")
    def test_real_z3_execution_is_digest_pinned_permitted_and_persisted(self) -> None:
        executable = Path(shutil.which("z3") or "").resolve()
        registration = ToolchainRegistration(
            "z3",
            executable,
            executable_digest(executable),
            version_args=("-version",),
            version_pattern=r"Z3 version",
        )
        runtime = FormalAssuranceRuntime(
            store=self.store,
            config=RuntimeConfig(
                artifact_root=self.root / "artifacts",
                execution_root=self.root / "executions",
                execution_permit_signer=self.signer,
                toolchains=(registration,),
            ),
        )
        subject = "subject-z3"
        production = self.execution_payload(
            skill_id="elmos-data-invariant-verifier",
            subject_id=subject,
            adapter_id="z3",
            files={
                "input.smt2": "(set-logic QF_LIA)\n(declare-const x Int)\n(assert (and (= x 1) (not (= x 1))))\n(check-sat)\n"
            },
            semantics="COUNTEREXAMPLE_SEARCH",
        )
        result = runtime.dispatch(
            "elmos-data-invariant-verifier",
            {
                "scope": self.scope.to_dict(),
                "subjectId": subject,
                "idempotencyKey": "z3-request",
                "facts": {"balance": 1},
                "productionExecution": production,
            },
            self.identity,
        )
        self.assertEqual(result["proofStatus"], "PROVED_SOLVER_TRUSTED")
        self.assertEqual(result["assuranceLevel"], "A2_SOLVER_PROVED")
        receipt = result["output"]["productionExecution"]
        self.assertEqual(receipt["state"], "COMPLETED")
        self.assertEqual(receipt["externalEvidenceStatus"], "NOT_RUN")
        persisted = self.store.get_execution_receipt(
            self.scope, receipt["executionId"]
        )
        self.assertEqual(persisted["bindingDigest"], receipt["bindingDigest"])
        with self.assertRaises(StoreError):
            self.store.get_execution_receipt(
                current_scope("tenant-b"), receipt["executionId"]
            )

    @unittest.skipUnless(shutil.which("z3"), "z3 is not installed")
    def test_native_execution_rejects_missing_role_and_one_time_permit_replay(self) -> None:
        executable = Path(shutil.which("z3") or "").resolve()
        registration = ToolchainRegistration(
            "z3",
            executable,
            executable_digest(executable),
            version_args=("-version",),
            version_pattern=r"Z3 version",
        )
        runtime = FormalAssuranceRuntime(
            store=self.store,
            config=RuntimeConfig(
                execution_permit_signer=self.signer,
                toolchains=(registration,),
            ),
        )
        subject = "subject-role"
        production = self.execution_payload(
            skill_id="elmos-data-invariant-verifier",
            subject_id=subject,
            adapter_id="z3",
            files={"input.smt2": "(set-logic QF_LIA)\n(assert false)\n(check-sat)\n"},
            semantics="COUNTEREXAMPLE_SEARCH",
            permit_id="permit-role",
            nonce="nonce-role",
        )
        request = {
            "scope": self.scope.to_dict(),
            "subjectId": subject,
            "idempotencyKey": "role-request",
            "facts": {},
            "productionExecution": production,
        }
        with self.assertRaises(ExecutionAuthorizationError):
            runtime.dispatch(
                "elmos-data-invariant-verifier",
                request,
                TrustedIdentity("tenant-a", "operator-a", "project-a"),
            )
        result = runtime.dispatch(
            "elmos-data-invariant-verifier", request, self.identity
        )
        self.assertEqual(result["proofStatus"], "PROVED_SOLVER_TRUSTED")
        with self.assertRaises(StoreError):
            runtime.dispatch(
                "elmos-data-invariant-verifier",
                {**request, "idempotencyKey": "replay-request"},
                self.identity,
            )

    def test_paths_unknown_fields_and_expired_or_tampered_permits_fail_closed(self) -> None:
        base = {
            "adapterId": "z3",
            "files": {"../input.smt2": "(check-sat)"},
            "options": {},
            "querySemantics": "COUNTEREXAMPLE_SEARCH",
            "timeoutSeconds": 10,
        }
        binding = execution_binding_digest(
            self.scope, "elmos-data-invariant-verifier", "subject-a", base
        )
        permit = self.signer.issue(
            permit_id="permit-path",
            nonce="nonce-path",
            scope=self.scope,
            skill_id="elmos-data-invariant-verifier",
            subject_id="subject-a",
            adapter_id="z3",
            execution_digest=binding,
        )
        with self.assertRaises(ExecutionContractError):
            NativeExecutionRequest.from_payload(
                {**base, "permit": permit.to_dict()},
                scope=self.scope,
                skill_id="elmos-data-invariant-verifier",
                subject_id="subject-a",
                limits=ResourceLimits(),
            )
        expired = self.signer.issue(
            permit_id="permit-expired",
            nonce="nonce-expired",
            scope=self.scope,
            skill_id="elmos-data-invariant-verifier",
            subject_id="subject-a",
            adapter_id="z3",
            execution_digest=binding,
            now_epoch=1,
        )
        with self.assertRaises(ExecutionAuthorizationError):
            self.signer.verify(
                expired,
                scope=self.scope,
                identity=self.identity,
                skill_id="elmos-data-invariant-verifier",
                subject_id="subject-a",
                adapter_id="z3",
                execution_digest=binding,
            )
        tampered = replace(permit, signature="hmac-sha256:" + "0" * 64)
        with self.assertRaises(ExecutionAuthorizationError):
            self.signer.verify(
                tampered,
                scope=self.scope,
                identity=self.identity,
                skill_id="elmos-data-invariant-verifier",
                subject_id="subject-a",
                adapter_id="z3",
                execution_digest=binding,
            )

    def test_sqlite_differential_executes_disposable_source_and_target(self) -> None:
        executor = SQLiteDifferentialExecutor(
            store=self.store,
            artifact_store=ContentAddressedArtifactStore(self.root / "cas"),
            permit_signer=self.signer,
            limits=ResourceLimits(),
        )
        skill = "elmos-sql-query-equivalence"
        subject = "subject-db"
        files = {
            "source/schema.sql": "create table t(id integer primary key, value text);",
            "source/seed.sql": "insert into t values(1, 'source');",
            "source/query.sql": "select id, value from t;",
            "target/schema.sql": "create table t(id integer primary key, value text);",
            "target/seed.sql": "insert into t values(1, 'target');",
            "target/query.sql": "select id, value from t;",
        }
        production = self.execution_payload(
            skill_id=skill,
            subject_id=subject,
            adapter_id="sqlite-differential",
            files=files,
            semantics="DIFFERENTIAL_EXECUTION",
            permit_id="permit-db",
            nonce="nonce-db",
        )
        receipt = executor.execute(
            scope=self.scope,
            identity=self.identity,
            skill_id=skill,
            subject_id=subject,
            payload={"productionExecution": production},
        )
        self.assertIsNotNone(receipt)
        assert receipt is not None
        self.assertEqual(receipt.proof_status, ProofStatus.REFUTED_WITH_COUNTEREXAMPLE)
        self.assertIn("queryRows", receipt.counterexample["mismatchedDimensions"])
        self.assertIn("state", receipt.counterexample["mismatchedDimensions"])

    def test_sqlite_differential_denies_file_escape_operations(self) -> None:
        executor = SQLiteDifferentialExecutor(
            store=self.store,
            artifact_store=None,
            permit_signer=self.signer,
            limits=ResourceLimits(),
        )
        skill = "elmos-sql-query-equivalence"
        subject = "subject-db-deny"
        files = {
            "source/schema.sql": "attach database '/tmp/escape.db' as escaped; create table t(id int);",
            "source/query.sql": "select 1;",
            "target/schema.sql": "create table t(id int);",
            "target/query.sql": "select 1;",
        }
        production = self.execution_payload(
            skill_id=skill,
            subject_id=subject,
            adapter_id="sqlite-differential",
            files=files,
            semantics="DIFFERENTIAL_EXECUTION",
            permit_id="permit-db-deny",
            nonce="nonce-db-deny",
        )
        with self.assertRaises(ExecutionAuthorizationError):
            executor.execute(
                scope=self.scope,
                identity=self.identity,
                skill_id=skill,
                subject_id=subject,
                payload={"productionExecution": production},
            )

    def test_conservative_parsers_cover_all_seventeen_adapters(self) -> None:
        positive_outputs = {
            "alive2": "Transformation seems to be correct!",
            "alloy": "No counterexample found",
            "apalache": "The outcome is: NoError",
            "boogie": "Boogie program verifier finished with 1 verified, 0 errors",
            "cvc5": "unsat\n",
            "dafny": "1 verified, 0 errors",
            "frama-c": "Proved goals: 100%",
            "jpf": "no errors detected",
            "k-framework": "normalized-output",
            "kani": "verification result: SUCCESS",
            "key": "Proof closed",
            "lean": "",
            "openjml": "ESC: 0 warnings",
            "sqlsolver": "Equivalent",
            "tlc": "Model checking completed. No error has been found.",
            "verieql": "Equivalent",
            "z3": "unsat\n",
        }
        dummy_permit = ExecutionPermit(
            permit_id="permit-parser",
            nonce="nonce-parser",
            tenant_id="tenant-a",
            account_id="account-a",
            project_id="project-a",
            skill_id="elmos-data-invariant-verifier",
            subject_id="subject-parser",
            adapter_id="z3",
            execution_digest="d" * 64,
            source_artifact_digest="a" * 64,
            target_artifact_digest="b" * 64,
            environment_digest="c" * 64,
            issued_at_epoch=1,
            expires_at_epoch=2,
            signature="hmac-sha256:" + "0" * 64,
        )
        for adapter_id in sorted(SOURCE_ADAPTERS):
            with self.subTest(adapter_id=adapter_id):
                output = positive_outputs[adapter_id].encode()
                options: dict[str, object] = {}
                semantics = "COUNTEREXAMPLE_SEARCH"
                if adapter_id == "k-framework":
                    options["expectedStdoutSha256"] = digest_bytes(output)
                    semantics = "DIFFERENTIAL_EXECUTION"
                request = NativeExecutionRequest(
                    adapter_id=adapter_id,
                    files=(ExecutionFile("fixture", b"x"),),
                    options=options,
                    query_semantics=semantics,
                    timeout_seconds=1,
                    permit=dummy_permit,
                    binding_digest="e" * 64,
                )
                process = ProcessExecutionResult(
                    state=ExecutionState.COMPLETED,
                    exit_code=0,
                    duration_ms=1,
                    stdout=output,
                    stderr=b"",
                    stdout_truncated=False,
                    stderr_truncated=False,
                    version_output="1.0",
                    containment="TEST",
                    command_digest="f" * 64,
                )
                status, assurance, diagnostics, counterexample = interpret_tool_result(
                    ADAPTERS[adapter_id], request, process
                )
                self.assertIn(
                    status,
                    {
                        ProofStatus.PROVED_SOLVER_TRUSTED,
                        ProofStatus.BOUNDED_NO_COUNTEREXAMPLE,
                    },
                )
                self.assertNotEqual(assurance, AssuranceLevel.NONE)
                self.assertFalse(diagnostics)
                self.assertIsNone(counterexample)

    def test_strong_sandbox_adapters_cannot_run_as_local_processes(self) -> None:
        executable = self.root / "fake-maven"
        executable.write_text("#!/bin/sh\necho 'fake 1.0'\n", encoding="utf-8")
        executable.chmod(0o755)
        registration = ToolchainRegistration(
            "maven-spring",
            executable,
            executable_digest(executable),
            version_pattern="fake 1.0",
            sandbox_kind=SandboxKind.LOCAL_PROCESS,
        )
        runtime = FormalAssuranceRuntime(
            store=self.store,
            config=RuntimeConfig(
                execution_permit_signer=self.signer,
                toolchains=(registration,),
            ),
        )
        subject = "subject-spring"
        production = self.execution_payload(
            skill_id="elmos-spring-route-binding-proof",
            subject_id=subject,
            adapter_id="maven-spring",
            files={"pom.xml": "<project/>", "src/Test.java": "class Test {}"},
            semantics="DIFFERENTIAL_EXECUTION",
            permit_id="permit-spring",
            nonce="nonce-spring",
        )
        with self.assertRaises(ExecutionAuthorizationError):
            runtime.dispatch(
                "elmos-spring-route-binding-proof",
                {
                    "scope": self.scope.to_dict(),
                    "subjectId": subject,
                    "idempotencyKey": "spring-request",
                    "routes": [],
                    "productionExecution": production,
                },
                self.identity,
            )


class _CaptureHandler(BaseHTTPRequestHandler):
    documents: list[dict[str, object]] = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        self.__class__.documents.append(json.loads(self.rfile.read(length)))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, format: str, *args: object) -> None:
        del format, args


class ObservabilityAndExplicitBindingTests(unittest.TestCase):
    def test_all_forty_production_methods_are_explicit_and_executable(self) -> None:
        store = StateStore()
        try:
            production = ProductionSkillExecutor(
                store=store,
                artifact_store=None,
                permit_signer=None,
                toolchains=(),
                limits=ResourceLimits(),
            )

            class FakeNative:
                def __init__(self) -> None:
                    self.calls: list[tuple[str, tuple[str, ...]]] = []

                def execute(self, **kwargs: object) -> NativeExecutionReceipt:
                    allowed = kwargs["allowed_adapters"]
                    assert isinstance(allowed, tuple) and allowed
                    self.calls.append((str(kwargs["skill_id"]), allowed))
                    return NativeExecutionReceipt(
                        execution_id="exec-fake",
                        adapter_id=allowed[0],
                        binding_digest="a" * 64,
                        toolchain_digest="b" * 64,
                        state=ExecutionState.COMPLETED,
                        proof_status=ProofStatus.BOUNDED_NO_COUNTEREXAMPLE,
                        assurance_level=AssuranceLevel.A1_BOUNDED,
                        started_at="2026-08-28T00:00:00Z",
                        duration_ms=1,
                        exit_code=0,
                        containment="FAKE_UNIT_BOUNDARY",
                        command_digest="c" * 64,
                        input_manifest_digest="d" * 64,
                        version_output_digest="e" * 64,
                        artifact_refs=(),
                        diagnostics=(),
                        counterexample=None,
                    )

            class FakeDatabase:
                def execute(self, **kwargs: object) -> NativeExecutionReceipt:
                    return NativeExecutionReceipt(
                        execution_id="exec-db-fake",
                        adapter_id="sqlite-differential",
                        binding_digest="a" * 64,
                        toolchain_digest="b" * 64,
                        state=ExecutionState.COMPLETED,
                        proof_status=ProofStatus.BOUNDED_NO_COUNTEREXAMPLE,
                        assurance_level=AssuranceLevel.A1_BOUNDED,
                        started_at="2026-08-28T00:00:00Z",
                        duration_ms=1,
                        exit_code=0,
                        containment="FAKE_DB_BOUNDARY",
                        command_digest="c" * 64,
                        input_manifest_digest="d" * 64,
                        version_output_digest="e" * 64,
                        artifact_refs=(),
                        diagnostics=(),
                        counterexample=None,
                    )

            fake_native = FakeNative()
            production.native = fake_native
            production.database = FakeDatabase()
            native_methods = (
                "api_contract", "architecture_constraint", "data_invariant",
                "generated_workflow", "requirement_spec", "resource_termination",
                "liveness_fairness", "tenant_noninterference", "verified_core",
                "concurrency_async", "cross_language_product", "effect_exception",
                "language_profile", "legacy_trace", "proof_carrying",
                "repository_composer", "rule_preservation", "semantic_gap",
                "semantic_ir", "java_jml", "spring_data", "spring_exception",
                "spring_order", "spring_proxy", "spring_route", "spring_security",
                "spring_session", "spring_transaction", "reflection_ffi",
            )
            database_methods = (
                "ddl_constraint", "dml_state", "dynamic_sql", "query_equivalence",
                "routine_contract", "schema_losslessness", "sql_semantic_ir",
                "sql_transaction", "sql_type_precision", "trigger_trace",
            )
            self.assertEqual(len(native_methods) + len(database_methods) + 1, 40)
            identity = TrustedIdentity("tenant-a", "actor-a", "project-a")
            for index, method_name in enumerate((*native_methods, *database_methods)):
                with self.subTest(method=method_name):
                    skill_id = f"skill-{index}"
                    context = SimpleNamespace(
                        skill_id=skill_id,
                        handler_id=f"execute_{index}",
                        scope=current_scope(),
                        subject_id=f"subject-{index}",
                        identity=identity,
                        payload={},
                    )
                    outcome = getattr(production, method_name)(
                        context, local_outcome(skill_id)
                    )
                    self.assertEqual(outcome.implementation_state, "PRODUCTION_CODE_COMPLETE")
                    self.assertIn("productionExecution", outcome.output)
            observability_context = SimpleNamespace(
                skill_id="elmos-formal-observability-slo",
                handler_id="execute_elmos_formal_observability_slo",
                scope=current_scope(),
                subject_id="subject-observe",
                identity=identity,
                payload={"objectives": {}},
            )
            observability_outcome = production.formal_observability(
                observability_context,
                local_outcome("elmos-formal-observability-slo"),
            )
            self.assertIn("runtimeSnapshot", observability_outcome.output)
        finally:
            store.close()

    def test_observability_exports_sanitized_digest_bound_snapshot(self) -> None:
        _CaptureHandler.documents = []
        server = ThreadingHTTPServer(("127.0.0.1", 0), _CaptureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        store = StateStore()
        signer = ExecutionPermitSigner(b"observability-production-key-0001")
        scope = current_scope()
        try:
            exporter = OtlpHttpJsonExporter(
                f"http://127.0.0.1:{server.server_port}/v1/metrics",
                {},
                allow_loopback_http=True,
            )
            service = FormalObservabilityService(store, exporter)
            service.record_invocation(
                scope,
                skill_id="elmos-data-invariant-verifier",
                proof_status="BOUNDED_NO_COUNTEREXAMPLE",
                duration_micros=100,
                trace_id="trace-observe",
            )
            production = ProductionSkillExecutor(
                store=store,
                artifact_store=None,
                permit_signer=signer,
                toolchains=(),
                limits=ResourceLimits(),
                observability=service,
            )
            snapshot = service.snapshot(scope)
            policy = json.dumps(
                {
                    "format": "elmos-formal-telemetry-export-policy/v1",
                    "snapshotDigest": digest_value(snapshot),
                },
                sort_keys=True,
            )
            raw: dict[str, object] = {
                "adapterId": "otlp-http",
                "files": {"export-policy.json": policy},
                "options": {},
                "querySemantics": "BOUNDARY_INVENTORY",
                "timeoutSeconds": 10,
            }
            skill_id = "elmos-formal-observability-slo"
            subject_id = "subject-observe"
            binding = execution_binding_digest(scope, skill_id, subject_id, raw)
            raw["permit"] = signer.issue(
                permit_id="permit-observe",
                nonce="nonce-observe",
                scope=scope,
                skill_id=skill_id,
                subject_id=subject_id,
                adapter_id="otlp-http",
                execution_digest=binding,
            ).to_dict()
            context = SimpleNamespace(
                skill_id=skill_id,
                handler_id="execute_elmos_formal_observability_slo",
                scope=scope,
                subject_id=subject_id,
                identity=TrustedIdentity(
                    "tenant-a", "operator-a", "project-a", ("formal-assurance:execute",)
                ),
                payload={"objectives": {}, "productionExecution": raw},
            )
            result = production.formal_observability(
                context, local_outcome(skill_id)
            )
            self.assertEqual(result.proof_status, ProofStatus.RUNTIME_MONITORED)
            self.assertEqual(len(_CaptureHandler.documents), 1)
            exported = _CaptureHandler.documents[0]
            self.assertNotIn("tenantId", json.dumps(exported))
            self.assertFalse(exported["tenantLabelsExported"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            store.close()


if __name__ == "__main__":
    unittest.main()
