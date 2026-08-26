import json
import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "framework-packs" / "spring-framework-5-3-mvc-to-spring-boot-3-5-3"
VALIDATOR = ROOT / "scripts" / "batch30" / "validate_legacy_spring_mvc_pack.py"
EMITTER = PACK / "target-profile/scaffold/materialize_target.py"
SOURCE_FIXTURE = PACK / "corpus/development/legacy-spring-mvc"


class LegacySpringMvcPackTests(unittest.TestCase):
    def run_validator(self, pack: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VALIDATOR), "--pack-dir", str(pack)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_checked_in_pack_is_exact_and_fail_closed(self):
        completed = self.run_validator(PACK)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn(
            "status=experimental decision=NOT_CERTIFIED execution=PASSED_LOCAL_EXACT_FIXTURE",
            completed.stdout,
        )

    def test_source_test_dependencies_are_exactly_pinned(self):
        pom = (PACK / "corpus/development/legacy-spring-mvc/pom.xml").read_text(
            encoding="utf-8"
        )
        self.assertIn("<hamcrest.version>2.2</hamcrest.version>", pom)
        self.assertIn("<json-path.version>2.7.0</json-path.version>", pom)
        self.assertIn("<artifactId>hamcrest</artifactId>", pom)
        self.assertIn("<artifactId>json-path</artifactId>", pom)

    def test_runtime_adapter_reports_current_partial_wiring(self):
        adapter = json.loads(
            (PACK / "adapters/runtime-adapter.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            "ROUTE_SELECTION_AND_TRUSTED_JAVA_EXACT_TARGET_MATERIALIZER_FAIL_CLOSED",
            adapter["implementation"],
        )
        self.assertEqual(
            "PRESENT_EXPERIMENTAL_PASSED_LOCAL_EXACT_FIXTURE",
            adapter["route_catalog_registration"],
        )
        self.assertEqual(
            "PRESENT_EXPERIMENTAL_EXACT_FIXTURE_MATERIALIZER_PASSED_LOCAL",
            adapter["local_execution_port_registration"],
        )
        self.assertEqual(
            "io.elmos.worker.SpringMvcExactTargetMaterializer",
            adapter["production_target_materializer"],
        )
        self.assertEqual("EXACT_FIXTURE_ONLY", adapter["production_target_materializer_scope"])
        self.assertEqual(
            "AFTER_PINNED_OPENREWRITE_BEFORE_TARGET_VERIFY",
            adapter["production_wiring_point"],
        )
        self.assertFalse(adapter["repository_python_execution"])
        self.assertRegex(adapter["trusted_input_manifest_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual("PASSED_LOCAL", adapter["execution_status"])
        self.assertEqual("PASSED_LOCAL", adapter["production_target_materializer_execution_status"])
        self.assertFalse(adapter["disabled_by_default"])

    def test_controlled_emitter_materializes_executable_war_without_claiming_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "target"
            completed = subprocess.run(
                [sys.executable, str(EMITTER), "--source", str(SOURCE_FIXTURE), "--output", str(output)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
            self.assertIn("MATERIALIZED_STATIC_NOT_RUNTIME_VERIFIED", completed.stdout)

            pom = (output / "pom.xml").read_text(encoding="utf-8")
            self.assertIn("<packaging>war</packaging>", pom)
            self.assertIn("<version>3.5.3</version>", pom)
            self.assertIn("<artifactId>tomcat-embed-jasper</artifactId>", pom)
            pom_root = ET.fromstring(pom)
            namespace = {"m": "http://maven.apache.org/POM/4.0.0"}
            jasper = next(
                dependency
                for dependency in pom_root.findall("m:dependencies/m:dependency", namespace)
                if dependency.findtext("m:artifactId", namespaces=namespace)
                == "tomcat-embed-jasper"
            )
            self.assertEqual("provided", jasper.findtext("m:scope", namespaces=namespace))
            self.assertIn("<artifactId>spring-boot-starter-actuator</artifactId>", pom)
            self.assertIn("<goal>repackage</goal>", pom)
            application = (output / "src/main/java/io/elmos/legacy/LegacyMvcApplication.java").read_text(encoding="utf-8")
            self.assertIn("extends SpringBootServletInitializer", application)
            configuration = (output / "src/main/java/io/elmos/legacy/boot/LegacyMvcConfiguration.java").read_text(encoding="utf-8")
            self.assertIn("DispatcherType.REQUEST, DispatcherType.ERROR", configuration)
            self.assertIn('addPathPatterns("/api/**")', configuration)
            self.assertIn("configureDefaultServletHandling", configuration)
            self.assertIn("configurer.enable()", configuration)
            self.assertIn('resolver.setPrefix("/WEB-INF/views/")', configuration)
            properties = (output / "src/main/resources/application.properties").read_text(encoding="utf-8")
            self.assertIn("legacy.orders.currency=CNY", properties)
            self.assertIn("legacy.orders.audit-header=X-Legacy-Audit", properties)
            self.assertIn("server.shutdown=graceful", properties)
            self.assertIn("server.servlet.register-default-servlet=true", properties)
            self.assertIn("management.endpoints.web.exposure.include=health", properties)
            boot_test = (output / "src/test/java/io/elmos/legacy/LegacyMvcApplicationTest.java").read_text(encoding="utf-8")
            self.assertIn('get("/orders")', boot_test)
            self.assertIn('view().name("orders/list")', boot_test)
            self.assertIn('get("/actuator/env")', boot_test)
            self.assertGreaterEqual(boot_test.count('doesNotExist("X-Legacy-Audit")'), 3)
            copied_source_test = (output / "src/test/java/io/elmos/legacy/web/LegacyOrderControllerTest.java").read_text(encoding="utf-8")
            self.assertIn("addMappedInterceptors", copied_source_test)
            self.assertNotIn(".addInterceptors(", copied_source_test)
            self.assertFalse((output / "src/main/webapp/WEB-INF/web.xml").exists())
            self.assertFalse((output / "src/main/resources/WEB-INF/spring/root-context.xml").exists())

            receipt = json.loads((output / ".elmos/migration-receipt.json").read_text(encoding="utf-8"))
            self.assertEqual("executable-war", receipt["exact_tuple"]["target"]["packaging"])
            self.assertTrue(all(value == "NOT_RUN" for value in receipt["execution"].values()))
            self.assertTrue(all(len(value) == 64 for value in receipt["generator_binding"].values()))
            self.assertEqual(5, len(receipt["source_inputs"]))
            self.assertTrue(all(len(item["sha256"]) == 64 for item in receipt["source_inputs"]))

    def test_controlled_emitter_refuses_existing_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "target"
            output.mkdir()
            marker = output / "owned.txt"
            marker.write_text("preserve", encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(EMITTER), "--source", str(SOURCE_FIXTURE), "--output", str(output)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(2, completed.returncode)
            self.assertIn("refusing to overwrite", completed.stderr)
            self.assertEqual("preserve", marker.read_text(encoding="utf-8"))

    def test_controlled_emitter_blocks_unknown_dependency(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "source"
            shutil.copytree(SOURCE_FIXTURE, copied, ignore=shutil.ignore_patterns("target"))
            pom_path = copied / "pom.xml"
            pom = pom_path.read_text(encoding="utf-8")
            dependency = """\n    <dependency>\n      <groupId>org.springframework.security</groupId>\n      <artifactId>spring-security-web</artifactId>\n      <version>5.8.15</version>\n    </dependency>"""
            pom_path.write_text(pom.replace("  </dependencies>", f"{dependency}\n  </dependencies>"), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(EMITTER), "--source", str(copied), "--output", str(Path(temporary) / "target")],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(2, completed.returncode)
            self.assertIn("source dependency graph must equal the exact admitted profile", completed.stderr)

    def test_controlled_emitter_blocks_unprofiled_jsp_tag_library(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "source"
            shutil.copytree(SOURCE_FIXTURE, copied, ignore=shutil.ignore_patterns("target"))
            jsp = copied / "src/main/webapp/WEB-INF/views/orders/list.jsp"
            jsp.write_text('<%@ taglib prefix="c" uri="jakarta.tags.core" %>\n' + jsp.read_text(encoding="utf-8"), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(EMITTER), "--source", str(copied), "--output", str(Path(temporary) / "target")],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(2, completed.returncode)
            self.assertIn("explicit JSP tag-library profile", completed.stderr)

    def test_controlled_emitter_blocks_dependency_scope_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "source"
            shutil.copytree(SOURCE_FIXTURE, copied, ignore=shutil.ignore_patterns("target"))
            pom_path = copied / "pom.xml"
            pom = pom_path.read_text(encoding="utf-8")
            pom_path.write_text(
                pom.replace("<scope>provided</scope>", "<scope>runtime</scope>", 1),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [sys.executable, str(EMITTER), "--source", str(copied), "--output", str(Path(temporary) / "target")],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(2, completed.returncode)
            self.assertIn("javax.servlet:javax.servlet-api scope must equal provided", completed.stderr)

    def test_controlled_emitter_blocks_build_plugin_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "source"
            shutil.copytree(SOURCE_FIXTURE, copied, ignore=shutil.ignore_patterns("target"))
            pom_path = copied / "pom.xml"
            pom = pom_path.read_text(encoding="utf-8")
            pom_path.write_text(pom.replace("<version>3.13.0</version>", "<version>3.12.1</version>"), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(EMITTER), "--source", str(copied), "--output", str(Path(temporary) / "target")],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(2, completed.returncode)
            self.assertIn("maven-compiler-plugin version must equal 3.13.0", completed.stderr)

    def test_controlled_emitter_blocks_interceptor_component_registration(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "source"
            shutil.copytree(SOURCE_FIXTURE, copied, ignore=shutil.ignore_patterns("target"))
            interceptor = copied / "src/main/java/io/elmos/legacy/web/RequestAuditInterceptor.java"
            source = interceptor.read_text(encoding="utf-8")
            source = source.replace(
                "import org.springframework.web.servlet.HandlerInterceptor;",
                "import org.springframework.stereotype.Component;\nimport org.springframework.web.servlet.HandlerInterceptor;",
            ).replace("public class RequestAuditInterceptor", "@Component\npublic class RequestAuditInterceptor")
            interceptor.write_text(source, encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(EMITTER), "--source", str(copied), "--output", str(Path(temporary) / "target")],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(2, completed.returncode)
            self.assertIn("component stereotypes must equal []", completed.stderr)

    def test_controlled_emitter_blocks_nested_mvc_graph_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "source"
            shutil.copytree(SOURCE_FIXTURE, copied, ignore=shutil.ignore_patterns("target"))
            context = copied / "src/main/resources/WEB-INF/spring/servlet-context.xml"
            xml = context.read_text(encoding="utf-8")
            context.write_text(
                xml.replace(
                    '<mvc:mapping path="/api/**"/>',
                    '<mvc:mapping path="/api/**"/>\n      <mvc:exclude-mapping path="/api/internal/**"/>',
                ),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [sys.executable, str(EMITTER), "--source", str(copied), "--output", str(Path(temporary) / "target")],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(2, completed.returncode)
            self.assertIn("MVC interceptor child graph is not the exact admitted contract", completed.stderr)

    def mutated_pack(self, temporary: str) -> tuple[Path, Path]:
        copied = Path(temporary) / PACK.name
        shutil.copytree(PACK, copied)
        pom_path = copied / "corpus/development/legacy-spring-mvc/pom.xml"
        return copied, pom_path

    def test_commented_property_token_does_not_satisfy_xml_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied, pom_path = self.mutated_pack(temporary)
            pom = pom_path.read_text(encoding="utf-8")
            pom = pom.replace(
                "    <hamcrest.version>2.2</hamcrest.version>",
                "    <!-- <hamcrest.version>2.2</hamcrest.version> -->",
            )
            pom_path.write_text(pom, encoding="utf-8")

            completed = self.run_validator(copied)
            self.assertEqual(1, completed.returncode)
            self.assertIn(
                "fixture POM property hamcrest.version must appear exactly once",
                completed.stderr,
            )

    def test_duplicate_property_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied, pom_path = self.mutated_pack(temporary)
            pom = pom_path.read_text(encoding="utf-8")
            token = "    <json-path.version>2.7.0</json-path.version>"
            pom_path.write_text(pom.replace(token, f"{token}\n{token}"), encoding="utf-8")

            completed = self.run_validator(copied)
            self.assertEqual(1, completed.returncode)
            self.assertIn(
                "fixture POM property json-path.version must appear exactly once",
                completed.stderr,
            )

    def test_wrong_property_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied, pom_path = self.mutated_pack(temporary)
            pom = pom_path.read_text(encoding="utf-8")
            pom_path.write_text(
                pom.replace(
                    "<hamcrest.version>2.2</hamcrest.version>",
                    "<hamcrest.version>2.1</hamcrest.version>",
                ),
                encoding="utf-8",
            )

            completed = self.run_validator(copied)
            self.assertEqual(1, completed.returncode)
            self.assertIn(
                "fixture POM property hamcrest.version must equal 2.2",
                completed.stderr,
            )

    def test_literal_dependency_version_cannot_replace_locked_expression(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied, pom_path = self.mutated_pack(temporary)
            pom = pom_path.read_text(encoding="utf-8")
            pom_path.write_text(
                pom.replace("<version>${json-path.version}</version>", "<version>2.7.0</version>"),
                encoding="utf-8",
            )

            completed = self.run_validator(copied)
            self.assertEqual(1, completed.returncode)
            self.assertIn(
                "fixture POM dependency com.jayway.jsonpath:json-path version "
                "must equal ${json-path.version}",
                completed.stderr,
            )

    def test_unearned_behavior_pass_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / PACK.name
            shutil.copytree(PACK, copied)
            certification_path = copied / "certification" / "certification.json"
            certification = json.loads(certification_path.read_text(encoding="utf-8"))
            certification["gate_results"]["behavior_equivalence"] = "PASSED"
            certification_path.write_text(json.dumps(certification, indent=2) + "\n", encoding="utf-8")

            completed = self.run_validator(copied)
            self.assertEqual(completed.returncode, 1)
            self.assertIn(
                "exact local runtime gate must be PASSED_LOCAL: behavior_equivalence",
                completed.stderr,
            )

    def test_external_gate_cannot_be_promoted_by_status_edit(self):
        for field in ("customer_acceptance", "independent_review", "external_certification"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                copied = Path(temporary) / PACK.name
                shutil.copytree(PACK, copied)
                certification_path = copied / "certification" / "certification.json"
                certification = json.loads(certification_path.read_text(encoding="utf-8"))
                certification["gate_results"][field] = "PASSED_LOCAL"
                certification_path.write_text(
                    json.dumps(certification, indent=2) + "\n",
                    encoding="utf-8",
                )

                completed = self.run_validator(copied)
                self.assertEqual(completed.returncode, 1)
                self.assertIn(
                    f"external or independent runtime gate must remain NOT_RUN: {field}",
                    completed.stderr,
                )

    def test_raw_evidence_tamper_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / PACK.name
            shutil.copytree(PACK, copied)
            summary = copied / "certification/local-execution/2026-08-26/evidence/target-test-summary.json"
            summary.write_bytes(summary.read_bytes() + b"\n")

            completed = self.run_validator(copied)
            self.assertEqual(completed.returncode, 1)
            self.assertIn(
                "indexed local evidence byte count mismatch: evidence/target-test-summary.json",
                completed.stderr,
            )

    def test_controlled_target_profile_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / PACK.name
            shutil.copytree(PACK, copied)
            profile = copied / "target-profile/profile.json"
            profile.write_bytes(profile.read_bytes() + b"\n")

            completed = self.run_validator(copied)
            self.assertEqual(completed.returncode, 1)
            self.assertIn(
                "controlled target profile pack resource drifted: target-profile/profile.json",
                completed.stderr,
            )

    def test_preserved_executable_war_tamper_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / PACK.name
            shutil.copytree(PACK, copied)
            executed_war = (
                copied
                / "certification/local-execution/2026-08-26/artifacts/"
                "executed-spring-boot-3.5.3.war"
            )
            executed_war.write_bytes(executed_war.read_bytes() + b"tamper")

            completed = self.run_validator(copied)
            self.assertEqual(completed.returncode, 1)
            self.assertIn(
                "indexed local evidence byte count mismatch: "
                "artifacts/executed-spring-boot-3.5.3.war",
                completed.stderr,
            )

    def test_semantic_receipt_tamper_fails_even_when_outer_digest_is_updated(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / PACK.name
            shutil.copytree(PACK, copied)
            evidence_root = copied / "certification/local-execution/2026-08-26"
            receipt_path = evidence_root / "local-qualification.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["target"]["executed_war"]["manifest"]["Start-Class"] = "example.Forged"
            receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
            index_path = evidence_root / "evidence-index.json"
            index = json.loads(index_path.read_text(encoding="utf-8"))
            item = next(entry for entry in index["files"] if entry["path"] == "local-qualification.json")
            item["bytes"] = receipt_path.stat().st_size
            item["sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
            index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")

            completed = self.run_validator(copied)
            self.assertEqual(completed.returncode, 1)
            self.assertIn("executed WAR manifest identity drifted", completed.stderr)

    def test_unearned_supported_capability_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / PACK.name
            shutil.copytree(PACK, copied)
            support_path = copied / "support-matrix.json"
            support = json.loads(support_path.read_text(encoding="utf-8"))
            support["capabilities"][0]["status"] = "supported"
            support_path.write_text(json.dumps(support, indent=2) + "\n", encoding="utf-8")

            completed = self.run_validator(copied)
            self.assertEqual(completed.returncode, 1)
            self.assertIn("cannot contain supported/certified capabilities", completed.stderr)


if __name__ == "__main__":
    unittest.main()
