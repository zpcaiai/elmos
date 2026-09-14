import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/operations/run_spring_nonboot_fcm_reference.py"
SPEC = importlib.util.spec_from_file_location("spring_nonboot_fcm_reference", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
REFERENCE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = REFERENCE
SPEC.loader.exec_module(REFERENCE)


class SpringNonBootFcmReferenceTests(unittest.TestCase):
    def test_executor_allowlists_only_the_four_exact_routes(self) -> None:
        self.assertEqual(
            set(REFERENCE.ROUTES),
            {
                "spring-mvc-3.2-5.2-maven-to-boot-3.5.3-java-21",
                "spring-framework-3.2-7.0-maven-to-boot-4.1.0-java-21",
                "spring-mvc-3.2-7.0-maven-to-boot-4.1.1-java-21",
                "spring-framework-3.2-7.0-maven-to-boot-4.1.1-java-21",
            },
        )

    def test_fcm_extraction_binds_exact_source_dependency_and_xml_graph(self) -> None:
        route = REFERENCE.ROUTES[
            "spring-mvc-3.2-5.2-maven-to-boot-3.5.3-java-21"
        ]
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            REFERENCE.materialize_source(source, route)
            fcm = REFERENCE.extract_fcm(source, route)
        self.assertEqual(fcm["route_id"], route.route_id)
        self.assertEqual(fcm["source"]["spring"], "5.2.25.RELEASE")
        self.assertEqual(fcm["beans"][0]["properties"], {
            "currency": "CNY",
            "multiplier": "125",
        })
        self.assertEqual(fcm["web"], {"dispatcher_mapping": "/"})

    def test_fcm_extraction_rejects_property_drift(self) -> None:
        route = REFERENCE.ROUTES[
            "spring-framework-3.2-7.0-maven-to-boot-4.1.0-java-21"
        ]
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            REFERENCE.materialize_source(source, route)
            context = source / "src/main/resources/application-context.xml"
            context.write_text(
                context.read_text(encoding="utf-8").replace(
                    'name="multiplier" value="125"',
                    'name="multiplier" value="126"',
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                REFERENCE.Failure, "FCM_PROPERTY_GRAPH_MISMATCH"
            ):
                REFERENCE.extract_fcm(source, route)

    def test_target_generator_rejects_unbound_route_identity(self) -> None:
        route = REFERENCE.ROUTES[
            "spring-framework-3.2-7.0-maven-to-boot-4.1.1-java-21"
        ]
        fcm = {
            "route_id": "another-route",
            "beans": [{"properties": {"currency": "CNY", "multiplier": "125"}}],
        }
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(
                REFERENCE.Failure, "FCM_TARGET_GENERATOR_INPUT_REJECTED"
            ):
                REFERENCE.materialize_target(Path(temporary), route, fcm)

    def test_executor_refuses_to_delete_a_nonempty_workspace(self) -> None:
        route = REFERENCE.ROUTES[
            "spring-framework-3.2-7.0-maven-to-boot-4.1.1-java-21"
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            sentinel = workspace / "user-owned.txt"
            sentinel.write_text("preserve", encoding="utf-8")
            previous = os.environ.copy()
            try:
                os.environ["ELMOS_MAVEN_EXECUTABLE"] = "/does/not/matter"
                os.environ["ELMOS_JAVA_11_HOME"] = "/does/not/matter"
                os.environ["ELMOS_JAVA_21_HOME"] = "/does/not/matter"
                with self.assertRaisesRegex(
                    REFERENCE.Failure, "WORKSPACE_MUST_BE_AN_EMPTY_DIRECTORY"
                ):
                    REFERENCE.execute(root, workspace, route)
            finally:
                os.environ.clear()
                os.environ.update(previous)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve")


if __name__ == "__main__":
    unittest.main()
