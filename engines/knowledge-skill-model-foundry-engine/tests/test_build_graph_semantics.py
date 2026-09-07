"""Real manifest parsing and fail-closed boundaries for the build graph handler."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from elmos_foundry.adapters import AdapterRegistry
from elmos_foundry.build_graph_semantics import SKILLS, build_build_graph_handlers
from elmos_foundry.canonical import canonical_digest, digest_bytes
from elmos_foundry.domain import TenantScope
from elmos_foundry.kernel import ExecutionKernel


SKILL = "build-and-dependency-graph"
SOURCE_INPUTS = ("normalized repository artifact", "build metadata", "runtime trace", "test result")
POM = '''<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion><groupId>example</groupId><artifactId>root</artifactId>
  <version>1.0.0</version><packaging>pom</packaging><modules><module>lib</module></modules>
  <properties><lib.version>2.0</lib.version></properties>
  <dependencyManagement><dependencies><dependency><groupId>example</groupId><artifactId>managed</artifactId>
    <version>3.0</version></dependency></dependencies></dependencyManagement>
  <dependencies><dependency><groupId>example</groupId><artifactId>lib</artifactId><version>${lib.version}</version>
    <optional>true</optional><exclusions><exclusion><groupId>example</groupId><artifactId>excluded</artifactId>
    </exclusion></exclusions></dependency></dependencies>
  <build><plugins><plugin><artifactId>build-helper-maven-plugin</artifactId><version>3.6.0</version>
    <executions><execution><id>generated</id><phase>generate-sources</phase><goals><goal>add-source</goal></goals>
    <configuration><sources><source>target/generated</source></sources></configuration></execution></executions>
  </plugin></plugins><pluginManagement><plugins><plugin><artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version></plugin></plugins></pluginManagement></build>
  <profiles><profile><id>ci</id><activation><property><name>env.CI</name></property></activation>
    <dependencies><dependency><groupId>org.junit.jupiter</groupId><artifactId>junit-jupiter</artifactId>
    <version>5.11.0</version><scope>test</scope></dependency></dependencies></profile></profiles>
</project>'''
CHILD_POM = '''<project><modelVersion>4.0.0</modelVersion><parent><groupId>example</groupId>
<artifactId>root</artifactId><version>1.0.0</version></parent><artifactId>lib</artifactId></project>'''


def fixture_inputs(skill: str, scope: TenantScope) -> dict[str, Any]:
    if skill != SKILL:
        raise ValueError("unknown build graph fixture")
    files = {
        "pom.xml": POM,
        "lib/pom.xml": CHILD_POM,
        "web/package.json": json.dumps({
            "name": "@example/web", "version": "1.0.0", "workspaces": ["packages/helper"],
            "dependencies": {"library": "^1.0.0", "@example/shared": "1.2.0"},
            "optionalDependencies": {"library": "2.0.0"}, "devDependencies": {"typescript": "5.7.2"},
            "peerDependencies": {"react": "^19.0.0"}, "scripts": {"build": "node tools/build.mjs"},
        }),
        "web/packages/helper/package.json": json.dumps({"name": "@example/helper", "version": "1.0.0"}),
    }
    return {
        "normalized repository artifact": {
            **{key: getattr(scope, key) for key in ("tenant_id", "project_id", "workspace_digest", "revision_set_id")},
            "files": [{"path": path, "content": text, "content_digest": digest_bytes(text.encode())} for path, text in files.items()],
        },
        "build metadata": {
            "parser_profiles": {path: "maven-pom-4.0.0" if path.endswith("pom.xml") else "npm-package-json-10" for path in files},
            "selected_maven_profiles": ["ci"], "baseline": {"status": "NOT_PROVIDED"},
        },
        "runtime trace": {"status": "NOT_RUN", "records": []},
        "test result": {"status": "NOT_RUN", "cases": []},
    }


def _replace(inputs: dict[str, Any], path: str, content: str) -> None:
    file = next(file for file in inputs["normalized repository artifact"]["files"] if file["path"] == path)
    file.update({"content": content, "content_digest": digest_bytes(content.encode())})


class BuildGraphSemanticTests(unittest.TestCase):
    def setUp(self) -> None:
        self.kernel = ExecutionKernel()
        self.scope = self.kernel.mint_context(
            tenant_id="tenant-a", project_id="project-a", actor_id="actor-a", environment_id="local",
            workspace_digest="sha256:" + "a" * 64, revision_set_id="sha256:" + "b" * 64,
            purpose="build-graph-acceptance", capabilities=("foundry.adapter.execute",), ttl_seconds=600,
        )
        catalog = SimpleNamespace(atomic_skills={SKILL: {}})
        self.handlers = build_build_graph_handlers(catalog, None)

    def execute(self, inputs: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {"operation": "local-semantic-execute", "inputs": inputs or fixture_inputs(SKILL, self.scope)}
        self.kernel.require_context(self.scope, "foundry.adapter.execute")
        AdapterRegistry._validate_adapter_payload(payload=payload, required_inputs=SOURCE_INPUTS)
        result = self.handlers[SKILL](SKILL, payload, self.scope, self.scope.invocation_id)
        self.assertEqual("SUCCEEDED", result["status"])
        self.assertEqual("NOT_RUN", result["external_evidence_status"])
        self.assertEqual("NOT_CERTIFIED", result["certification_status"])
        return dict(result["outputs"])

    def test_exact_registry_and_required_outer_shapes(self) -> None:
        self.assertEqual(SKILLS, set(self.handlers))
        outputs = self.execute()
        self.assertEqual({"semantic graph", "architecture model", "semantic diff", "confidence report"}, set(outputs))
        self.assertTrue(all(value not in ({}, [], "", None) for value in outputs.values()))
        for field in SOURCE_INPUTS:
            for empty in (None, "", {}, []):
                inputs = fixture_inputs(SKILL, self.scope)
                inputs[field] = empty
                with self.subTest(field=field, empty=empty), self.assertRaises(ValueError):
                    self.execute(inputs)

    def test_real_maven_modules_management_plugins_and_profiles_are_distinct(self) -> None:
        outputs = self.execute()
        graph = outputs["semantic graph"]
        nodes = graph["nodes"]
        self.assertEqual(4, len([node for node in nodes if node["kind"] == "module"]))
        self.assertEqual(2, len([edge for edge in graph["edges"] if edge["kind"] == "references-inventory-module"]))
        managed = next(node for node in nodes if node["name"] == "example:managed")
        self.assertTrue(managed["attributes"]["managed"])
        self.assertTrue(any(edge["target_node"] == managed["id"] and edge["kind"] == "manages-dependency" for edge in graph["edges"]))
        library = next(node for node in nodes if node["name"] == "example:lib" and node["kind"] == "dependency-declaration")
        self.assertEqual("${lib.version}", library["attributes"]["requested_spec"])
        self.assertTrue(library["attributes"]["optional"])
        self.assertEqual([{"group_id": "example", "artifact_id": "excluded"}], library["attributes"]["exclusions"])
        profile = next(node for node in nodes if node["kind"] == "profile-declaration")
        self.assertTrue(profile["attributes"]["requested_selection"])
        self.assertEqual("NOT_RUN", profile["attributes"]["native_activation"])
        self.assertTrue(any(edge["condition"] == "profile:ci" for edge in graph["edges"]))
        execution = next(node for node in nodes if node["kind"] == "plugin-execution-declaration")
        self.assertEqual("generate-sources", execution["attributes"]["phase"])
        self.assertEqual(["add-source"], execution["attributes"]["goals"])
        self.assertEqual("NOT_RUN", execution["attributes"]["execution_status"])

    def test_npm_dependency_scopes_optional_override_and_scripts_are_preserved(self) -> None:
        graph = self.execute()["semantic graph"]
        declarations = [node for node in graph["nodes"] if node["ecosystem"] == "npm" and node["kind"] == "dependency-declaration"]
        self.assertEqual(5, len(declarations))
        runtime = next(node for node in declarations if node["name"] == "library" and node["attributes"]["declaration_scope"] == "dependencies")
        self.assertTrue(runtime["attributes"]["overridden_by_optional_declaration"])
        self.assertEqual("^1.0.0", runtime["attributes"]["requested_spec"])
        self.assertTrue(all(node["attributes"]["resolution_status"] == "NOT_RUN" for node in declarations))
        script = next(node for node in graph["nodes"] if node["kind"] == "script-declaration")
        self.assertEqual(canonical_digest("node tools/build.mjs"), script["attributes"]["body_digest"])
        self.assertEqual("NOT_RUN", script["attributes"]["execution_status"])

    def test_maven_empty_parent_lookup_and_imported_bom_are_explicit_declarations(self) -> None:
        inputs = fixture_inputs(SKILL, self.scope)
        _replace(inputs, "lib/pom.xml", CHILD_POM.replace("</parent>", "<relativePath/></parent>"))
        bom = POM.replace("<artifactId>managed</artifactId>", "<artifactId>managed</artifactId><type>pom</type><scope>import</scope>")
        _replace(inputs, "pom.xml", bom)
        outputs = self.execute(inputs)
        node = next(node for node in outputs["semantic graph"]["nodes"] if node["name"] == "example:managed")
        self.assertEqual("import", node["attributes"]["scope"])
        self.assertEqual("NOT_RUN", node["attributes"]["resolution_status"])
        parent = next(item for item in outputs["confidence report"]["diagnostics"] if item["code"] == "maven-parent-inheritance-not-evaluated")
        self.assertEqual("", parent["details"]["relative_path"])

    def test_invalid_maven_dependency_scopes_cannot_be_normalized_into_success(self) -> None:
        for scope in ("unknown", "import", "system"):
            inputs = fixture_inputs(SKILL, self.scope)
            _replace(inputs, "pom.xml", POM.replace("<optional>true</optional>", f"<optional>true</optional><scope>{scope}</scope>"))
            with self.subTest(scope=scope), self.assertRaises(ValueError):
                self.execute(inputs)

    def test_parent_declaration_changes_are_visible_without_evaluating_inheritance(self) -> None:
        inputs = fixture_inputs(SKILL, self.scope)
        baseline = self.execute(inputs)["semantic graph"]
        _replace(inputs, "lib/pom.xml", CHILD_POM.replace("<version>1.0.0</version>", "<version>2.0.0</version>"))
        inputs["build metadata"]["baseline"] = {"status": "PROVIDED", "graph": baseline}
        outputs = self.execute(inputs)
        module = next(node for node in outputs["semantic graph"]["nodes"] if node["kind"] == "module" and node["source"]["path"] == "lib/pom.xml")
        self.assertEqual("2.0.0", module["attributes"]["parent_declaration"]["version"])
        self.assertEqual("NOT_RUN", module["attributes"]["inheritance_evaluation"])
        self.assertEqual([module["id"]], outputs["semantic diff"]["nodes"]["changed"])
        self.assertEqual([], outputs["semantic diff"]["nodes"]["added"])
        self.assertEqual([], outputs["semantic diff"]["nodes"]["removed"])

    def test_unknown_children_of_recognized_maven_containers_are_reported(self) -> None:
        containers = {
            "dependencies": "maven-dependencies-fields-not-modeled",
            "dependencies/dependency/exclusions": "maven-exclusions-fields-not-modeled",
            "dependencies/dependency/exclusions/exclusion": "maven-exclusion-fields-not-modeled",
            "dependencyManagement": "maven-dependency-management-fields-not-modeled",
            "modules": "maven-modules-fields-not-modeled",
            "build/plugins": "maven-plugins-fields-not-modeled",
            "build/pluginManagement": "maven-plugin-management-fields-not-modeled",
            "build/plugins/plugin/executions": "maven-executions-fields-not-modeled",
            "build/plugins/plugin/executions/execution": "maven-execution-fields-not-modeled",
            "build/plugins/plugin/executions/execution/goals": "maven-goals-fields-not-modeled",
            "profiles": "maven-profiles-fields-not-modeled",
        }
        namespace = "{http://maven.apache.org/POM/4.0.0}"
        for path, code in containers.items():
            with self.subTest(path=path):
                root = ET.fromstring(POM)
                container = root.find("/".join(namespace + part for part in path.split("/")))
                self.assertIsNotNone(container)
                assert container is not None
                ET.SubElement(container, namespace + "futureDeclaration").text = "unmodeled"
                inputs = fixture_inputs(SKILL, self.scope)
                _replace(inputs, "pom.xml", ET.tostring(root, encoding="unicode"))
                diagnostics = self.execute(inputs)["confidence report"]["diagnostics"]
                self.assertTrue(any(row["code"] == code and "futureDeclaration" in row["details"] for row in diagnostics))

    def test_paths_with_control_characters_are_rejected(self) -> None:
        for character in ("\x00", "\t", "\r", "\n", "\x7f"):
            inputs = fixture_inputs(SKILL, self.scope)
            path = "folder" + character + "/pom.xml"
            inputs["normalized repository artifact"]["files"][0]["path"] = path
            inputs["build metadata"]["parser_profiles"][path] = inputs["build metadata"]["parser_profiles"].pop("pom.xml")
            with self.subTest(character=repr(character)), self.assertRaises(ValueError):
                self.execute(inputs)

    def test_sources_point_to_real_manifest_elements_and_json_values(self) -> None:
        inputs = fixture_inputs(SKILL, self.scope)
        files = {file["path"]: file["content"] for file in inputs["normalized repository artifact"]["files"]}
        graph = self.execute(inputs)["semantic graph"]
        for row in [*graph["nodes"], *graph["edges"]]:
            source = row["source"]
            content = files[source["path"]]
            self.assertEqual("sha256:" + hashlib.sha256(content.encode()).hexdigest(), source["content_digest"])
            if source["locator_format"] == "json-pointer":
                value = json.loads(content)
                for part in source["locator"].split("/")[1:]:
                    key = part.replace("~1", "/").replace("~0", "~")
                    value = value[int(key)] if isinstance(value, list) else value[key]
                self.assertIsNotNone(value)
            else:
                element = ET.fromstring(content)
                for part in source["locator"].split("/")[2:]:
                    tag, _, index = part.partition("[")
                    matches = [child for child in element if child.tag.rsplit("}", 1)[-1] == tag]
                    element = matches[int(index[:-1]) - 1]
                self.assertIsNotNone(element)

    def test_scope_mismatch_is_rejected_before_parsing(self) -> None:
        for key, value in (("tenant_id", "foreign"), ("project_id", "foreign"), ("workspace_digest", "sha256:" + "c" * 64), ("revision_set_id", "sha256:" + "c" * 64)):
            inputs = fixture_inputs(SKILL, self.scope)
            inputs["normalized repository artifact"][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "authenticated scope"):
                self.execute(inputs)

    def test_path_digest_and_exact_inventory_boundaries(self) -> None:
        for case in ("absolute", "traversal", "duplicate", "digest", "unmatched-profile", "unsupported-profile"):
            inputs = fixture_inputs(SKILL, self.scope)
            files = inputs["normalized repository artifact"]["files"]
            if case == "absolute":
                files[0]["path"] = "/etc/passwd"
            elif case == "traversal":
                files[0]["path"] = "../pom.xml"
            elif case == "duplicate":
                files.append(deepcopy(files[0]))
            elif case == "digest":
                files[0]["content"] += "changed"
            elif case == "unmatched-profile":
                inputs["build metadata"]["parser_profiles"]["unused/pom.xml"] = "maven-pom-4.0.0"
            else:
                inputs["build metadata"]["parser_profiles"]["pom.xml"] = "gradle-8"
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.execute(inputs)

    def test_duplicate_json_keys_and_malformed_manifests_fail_closed(self) -> None:
        cases = (
            ("web/package.json", '{"name":"a","name":"b"}'),
            ("web/package.json", '{"name":"a","dependencies":{"a":"1","a":"2"}}'),
            ("web/package.json", '{"name":"a","optionalDependencies":null}'),
            ("pom.xml", "<project><broken></project>"),
            ("pom.xml", POM.replace("<modelVersion>4.0.0</modelVersion>", "<modelVersion>4.1.0</modelVersion>")),
            ("pom.xml", POM.replace("<artifactId>root</artifactId>", "<artifactId>root</artifactId><artifactId>duplicate</artifactId>", 1)),
        )
        for path, content in cases:
            inputs = fixture_inputs(SKILL, self.scope)
            _replace(inputs, path, content)
            with self.subTest(path=path, content=content[:60]), self.assertRaises(ValueError):
                self.execute(inputs)

    def test_xml_dtd_and_entities_cannot_access_local_or_remote_resources(self) -> None:
        for declaration in ('<!DOCTYPE project SYSTEM "https://example.invalid/private.dtd">', '<!DOCTYPE project [<!ENTITY secret SYSTEM "file:///etc/passwd">]>'):
            inputs = fixture_inputs(SKILL, self.scope)
            _replace(inputs, "pom.xml", declaration + POM)
            with patch("builtins.open", side_effect=AssertionError("filesystem opened")), patch("socket.socket", side_effect=AssertionError("network opened")):
                with self.assertRaisesRegex(ValueError, "DTD"):
                    self.execute(inputs)

    def test_source_scripts_and_plugin_configuration_are_never_executed(self) -> None:
        inputs = fixture_inputs(SKILL, self.scope)
        npm = json.loads(next(file["content"] for file in inputs["normalized repository artifact"]["files"] if file["path"] == "web/package.json"))
        npm["scripts"]["install"] = "python -c 'raise RuntimeError(123)'"
        _replace(inputs, "web/package.json", json.dumps(npm))
        with patch("subprocess.run", side_effect=AssertionError("command executed")), patch("builtins.open", side_effect=AssertionError("filesystem opened")), patch("socket.socket", side_effect=AssertionError("network opened")):
            outputs = self.execute(inputs)
        self.assertEqual("NOT_RUN", outputs["confidence report"]["native_build_status"])
        self.assertFalse(outputs["confidence report"]["whole_repository_complete"])

    def test_missing_modules_patterns_and_unknown_fields_remain_explicit(self) -> None:
        inputs = fixture_inputs(SKILL, self.scope)
        npm = {"name": "app", "workspaces": ["missing", "packages/*"], "engines": {"node": ">=22"}}
        _replace(inputs, "web/package.json", json.dumps(npm))
        outputs = self.execute(inputs)
        codes = {item["code"] for item in outputs["confidence report"]["diagnostics"]}
        self.assertTrue({"referenced-module-not-in-supplied-inventory", "module-pattern-or-property-not-expanded", "npm-fields-not-semantically-modeled"}.issubset(codes))

    def test_native_success_claims_are_not_accepted_as_execution_evidence(self) -> None:
        for field in ("runtime trace", "test result"):
            inputs = fixture_inputs(SKILL, self.scope)
            inputs[field]["status"] = "PASS"
            with self.assertRaisesRegex(ValueError, "cannot manufacture native verification"):
                self.execute(inputs)

    def test_graph_and_diff_are_deterministic_and_compare_real_dependency_changes(self) -> None:
        inputs = fixture_inputs(SKILL, self.scope)
        before = self.execute(inputs)["semantic graph"]
        self.assertEqual(before, self.execute(inputs)["semantic graph"])
        inputs["build metadata"]["baseline"] = {"status": "PROVIDED", "graph": before}
        _replace(inputs, "pom.xml", POM.replace("<version>3.0</version>", "<version>3.1</version>"))
        outputs = self.execute(inputs)
        diff = outputs["semantic diff"]
        self.assertEqual("COMPARED", diff["status"])
        self.assertEqual(1, len(diff["nodes"]["changed"]))
        self.assertEqual([], diff["nodes"]["added"])
        self.assertEqual([], diff["nodes"]["removed"])
        self.assertEqual([], diff["edges"]["changed"])

    def test_baseline_digest_scope_duplicate_and_dangling_edges_fail_closed(self) -> None:
        original = self.execute()["semantic graph"]
        for case in ("digest", "scope", "duplicate", "dangling"):
            graph = deepcopy(original)
            if case == "digest":
                graph["graph_digest"] = "sha256:" + "0" * 64
            elif case == "scope":
                graph["scope"]["tenant_id"] = "foreign"
            elif case == "duplicate":
                graph["nodes"].append(deepcopy(graph["nodes"][0]))
            else:
                graph["edges"][0]["target_node"] = "missing-node"
            if case != "digest":
                graph["graph_digest"] = canonical_digest({key: value for key, value in graph.items() if key != "graph_digest"})
            inputs = fixture_inputs(SKILL, self.scope)
            inputs["build metadata"]["baseline"] = {"status": "PROVIDED", "graph": graph}
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.execute(inputs)

    def test_xml_depth_and_graph_size_are_bounded(self) -> None:
        inputs = fixture_inputs(SKILL, self.scope)
        deep = '<project><modelVersion>4.0.0</modelVersion><artifactId>a</artifactId>' + '<x>' * 40 + '</x>' * 40 + '</project>'
        _replace(inputs, "pom.xml", deep)
        with self.assertRaisesRegex(ValueError, "structural bounds"):
            self.execute(inputs)
        inputs = fixture_inputs(SKILL, self.scope)
        _replace(inputs, "web/package.json", json.dumps({"name": "large", "dependencies": {f"package-{i}": "1" for i in range(513)}}))
        with self.assertRaisesRegex(ValueError, "512 nodes"):
            self.execute(inputs)


if __name__ == "__main__":
    unittest.main()
