"""Exact declaration graphs for Maven POM 4.0.0 and npm 10 package.json.

Real XML/JSON parsers construct typed, source-addressed declarations. This
handler never evaluates Maven properties, merges inherited/effective POMs,
resolves package versions, runs lifecycle commands, reads a caller path, or
claims native execution. Only supplied, scope-bound manifest bytes are read.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Any
import xml.etree.ElementTree as ET

from .canonical import canonical_digest, canonical_value, digest_bytes, strict_json_loads, validate_digest
from .domain import TenantScope
from .local_semantics import CatalogView, LocalHandler, _exact_mapping, _mapping, _response, _sequence, _text
from .store import FoundryStore


SKILLS = frozenset({"build-and-dependency-graph"})
INPUTS = ("normalized repository artifact", "build metadata", "runtime trace", "test result")
PROFILES = {"maven-pom-4.0.0": "pom.xml", "npm-package-json-10": "package.json"}
SCHEMA_VERSION = "elmos.foundry.build-declaration-graph.v1"
_MAVEN_NS = "http://maven.apache.org/POM/4.0.0"


class NodeKind(StrEnum):
    MODULE = "module"
    DEPENDENCY = "dependency-declaration"
    PLUGIN = "plugin-declaration"
    EXECUTION = "plugin-execution-declaration"
    PROFILE = "profile-declaration"
    PROPERTY = "property-declaration"
    SCRIPT = "script-declaration"
    MODULE_REFERENCE = "module-reference"


class EdgeKind(StrEnum):
    DEPENDS = "declares-dependency"
    MANAGES = "manages-dependency"
    CONTAINS = "contains-declaration"
    PLUGIN = "declares-plugin"
    MANAGES_PLUGIN = "manages-plugin"
    EXECUTION = "declares-execution"
    MODULE = "references-inventory-module"


@dataclass(frozen=True)
class SourceRef:
    path: str
    content_digest: str
    locator: str
    locator_format: str


@dataclass(frozen=True)
class BuildNode:
    id: str
    kind: str
    ecosystem: str
    name: str
    attributes: Mapping[str, Any]
    source: SourceRef


@dataclass(frozen=True)
class BuildEdge:
    id: str
    source_node: str
    target_node: str
    kind: str
    condition: str
    source: SourceRef


def _path(value: Any) -> str:
    text = _text(value, "manifest path", maximum=512)
    parsed = PurePosixPath(text)
    if (parsed.is_absolute() or "\\" in text or any(ord(character) < 32 or ord(character) == 127 for character in text) or parsed.as_posix() != text
            or any(part in {"", ".", ".."} for part in text.split("/"))):
        raise ValueError("manifest path must be canonical and repository-relative")
    return text


def _text_list(value: Any, label: str, *, maximum: int = 128) -> list[str]:
    result = [_text(item, label, maximum=512) for item in _sequence(value, label, minimum=0, maximum=maximum)]
    if len(set(result)) != len(result):
        raise ValueError(f"{label} contains duplicates")
    return result


def _pointer(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


class _NoDtdBuilder(ET.TreeBuilder):
    def doctype(self, name: str, pubid: str | None, system: str | None) -> None:
        raise ValueError("DTD and entity declarations are not permitted")


class _Graph:
    def __init__(self, scope: Mapping[str, Any]) -> None:
        self.scope = scope
        self.nodes: dict[str, BuildNode] = {}
        self.edges: dict[str, BuildEdge] = {}
        self.modules: dict[str, str] = {}
        self.references: list[tuple[str, str, SourceRef, str]] = []
        self.diagnostics: list[Mapping[str, Any]] = []

    def node(self, kind: NodeKind, ecosystem: str, name: str, attrs: Mapping[str, Any], source: SourceRef) -> str:
        identity = "n-" + canonical_digest({"path": source.path, "locator": source.locator, "kind": kind.value})[7:]
        if identity in self.nodes:
            raise ValueError("duplicate graph declaration identity")
        if len(self.nodes) >= 512:
            raise ValueError("build declaration graph exceeds 512 nodes")
        self.nodes[identity] = BuildNode(identity, kind.value, ecosystem, name, attrs, source)
        return identity

    def edge(self, owner: str, target: str, kind: EdgeKind, source: SourceRef, condition: str = "always") -> None:
        if owner not in self.nodes or target not in self.nodes:
            raise ValueError("graph edge refers to a missing declaration")
        identity = "e-" + canonical_digest({"source": owner, "target": target, "kind": kind.value, "condition": condition})[7:]
        if identity in self.edges:
            raise ValueError("duplicate graph edge")
        if len(self.edges) >= 1024:
            raise ValueError("build declaration graph exceeds 1024 edges")
        self.edges[identity] = BuildEdge(identity, owner, target, kind.value, condition, source)

    def diagnostic(self, code: str, source: SourceRef, details: Any) -> None:
        self.diagnostics.append({"code": code, "source": asdict(source), "details": details})

    def module_reference(self, owner: str, declared: str, source: SourceRef, condition: str, filename: str) -> None:
        reference = self.node(NodeKind.MODULE_REFERENCE, self.nodes[owner].ecosystem, declared,
                              {"resolution": "DECLARATION_ONLY"}, source)
        self.edge(owner, reference, EdgeKind.CONTAINS, source, condition)
        if any(marker in declared for marker in ("*", "?", "[", "]", "{", "}", "$")):
            self.diagnostic("module-pattern-or-property-not-expanded", source, declared)
            return
        try:
            relative = _path(declared)
        except ValueError:
            self.diagnostic("module-path-outside-supported-profile", source, declared)
            return
        path = (PurePosixPath(source.path).parent / relative / filename).as_posix()
        self.references.append((reference, path, source, condition))

    def finish(self) -> dict[str, Any]:
        for owner, path, source, condition in self.references:
            if path in self.modules:
                self.edge(owner, self.modules[path], EdgeKind.MODULE, source, condition)
            else:
                self.diagnostic("referenced-module-not-in-supplied-inventory", source, path)
        body = {
            "schema_version": SCHEMA_VERSION, "scope": dict(self.scope),
            "nodes": [asdict(self.nodes[key]) for key in sorted(self.nodes)],
            "edges": [asdict(self.edges[key]) for key in sorted(self.edges)],
        }
        return {**body, "graph_digest": canonical_digest(body)}


def _npm(graph: _Graph, path: str, content: str, digest: str) -> None:
    document = _mapping(strict_json_loads(content), "package.json")
    name = _text(document.get("name"), "npm package name", maximum=214)
    version = document.get("version")
    if version is not None:
        _text(version, "npm declared version", maximum=128)
    def source(pointer: str) -> SourceRef:
        return SourceRef(path, digest, pointer, "json-pointer")

    owner = graph.node(NodeKind.MODULE, "npm", name, {"version": version, "parser_profile": "npm-package-json-10"}, source(""))
    graph.modules[path] = owner
    sections = ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies")
    section_maps = {section: _mapping(document.get(section, {}), section) for section in sections}
    for section in sections:
        dependencies = section_maps[section]
        for dependency, spec in sorted(dependencies.items()):
            _text(dependency, "dependency name", maximum=214)
            _text(spec, "dependency specification", maximum=1024)
            ref = source(f"/{section}/{_pointer(dependency)}")
            node = graph.node(NodeKind.DEPENDENCY, "npm", dependency, {
                "requested_spec": spec, "declaration_scope": section,
                "resolution_status": "NOT_RUN",
                "overridden_by_optional_declaration": section == "dependencies" and dependency in section_maps["optionalDependencies"],
            }, ref)
            graph.edge(owner, node, EdgeKind.DEPENDS, ref)
    scripts = _mapping(document.get("scripts", {}), "scripts")
    for name, command in sorted(scripts.items()):
        _text(name, "script name", maximum=128)
        _text(command, "script body", maximum=8192)
        ref = source(f"/scripts/{_pointer(name)}")
        node = graph.node(NodeKind.SCRIPT, "npm", name, {
            "body_digest": canonical_digest(command), "execution_status": "NOT_RUN",
        }, ref)
        graph.edge(owner, node, EdgeKind.CONTAINS, ref)
    if "workspaces" in document:
        workspaces = _text_list(document["workspaces"], "npm workspaces", maximum=32)
        for index, workspace in enumerate(workspaces):
            graph.module_reference(owner, workspace, source(f"/workspaces/{index}"), "always", "package.json")
    recognized = {"name", "version", *sections, "scripts", "workspaces"}
    unmodeled = sorted(set(document) - recognized)
    if unmodeled:
        graph.diagnostic("npm-fields-not-semantically-modeled", source(""), unmodeled)


def _maven(graph: _Graph, path: str, content: str, digest: str, selected_profiles: set[str]) -> None:
    try:
        root = ET.fromstring(content, parser=ET.XMLParser(target=_NoDtdBuilder()))
    except ET.ParseError as exc:
        raise ValueError(f"malformed Maven XML: {exc}") from exc
    if root.tag not in {"project", f"{{{_MAVEN_NS}}}project"}:
        raise ValueError("unsupported Maven project root or namespace")
    namespace = f"{{{_MAVEN_NS}}}" if root.tag.startswith("{") else ""
    locations: dict[int, str] = {}
    stack = [(root, "/project[1]", 0)]
    while stack:
        element, location, depth = stack.pop()
        if len(locations) >= 4096 or depth > 32:
            raise ValueError("Maven XML exceeds structural bounds")
        if namespace and not element.tag.startswith(namespace):
            raise ValueError("foreign namespace within Maven POM")
        if not namespace and element.tag.startswith("{"):
            raise ValueError("foreign namespace within Maven POM")
        locations[id(element)] = location
        counts: Counter[str] = Counter()
        for descendant in element:
            tag = descendant.tag.removeprefix(namespace)
            counts[tag] += 1
            stack.append((descendant, f"{location}/{tag}[{counts[tag]}]", depth + 1))

    def children(element: ET.Element, name: str) -> list[ET.Element]:
        return element.findall(namespace + name)

    def child(element: ET.Element, name: str) -> ET.Element | None:
        matches = children(element, name)
        if len(matches) > 1:
            raise ValueError(f"duplicate singleton Maven element: {name}")
        return matches[0] if matches else None

    def scalar(element: ET.Element, name: str, default: str | None = None, *, allow_empty: bool = False) -> str | None:
        item = child(element, name)
        if item is None:
            return default
        if len(item):
            raise ValueError(f"Maven scalar {name} contains nested elements")
        text = (item.text or "").strip()
        return "" if allow_empty and not text else _text(text, name, maximum=4096)

    def source(element: ET.Element) -> SourceRef:
        return SourceRef(path, digest, locations[id(element)], "maven-element-path")

    def unmodeled_fields(element: ET.Element, modeled: set[str], code: str) -> None:
        extra = sorted({item.tag.removeprefix(namespace) for item in element} - modeled)
        if extra:
            graph.diagnostic(code, source(element), extra)

    if scalar(root, "modelVersion") != "4.0.0":
        raise ValueError("only Maven POM modelVersion 4.0.0 is supported")
    artifact = scalar(root, "artifactId")
    if artifact is None:
        raise ValueError("Maven artifactId is required")
    parent = child(root, "parent")
    group = scalar(root, "groupId")
    version = scalar(root, "version")
    parent_declaration = None if parent is None else {
        "group_id": scalar(parent, "groupId"), "artifact_id": scalar(parent, "artifactId"),
        "version": scalar(parent, "version"), "relative_path": scalar(parent, "relativePath", "../pom.xml", allow_empty=True),
    }
    if parent_declaration is not None and any(parent_declaration[key] is None for key in ("group_id", "artifact_id", "version")):
        raise ValueError("Maven parent requires exact group, artifact and version declarations")
    owner = graph.node(NodeKind.MODULE, "maven", f"{group or '<inherited>'}:{artifact}", {
        "group_id": group, "artifact_id": artifact, "version": version,
        "packaging": scalar(root, "packaging", "jar"), "parser_profile": "maven-pom-4.0.0",
        "inheritance_evaluation": "NOT_RUN", "parent_declaration": parent_declaration,
    }, source(root))
    graph.modules[path] = owner
    if parent is not None:
        graph.diagnostic("maven-parent-inheritance-not-evaluated", source(parent), parent_declaration)
        unmodeled_fields(parent, {"groupId", "artifactId", "version", "relativePath"}, "maven-parent-fields-not-modeled")

    def dependencies(container: ET.Element | None, declared_by: str, condition: str, managed: bool = False) -> None:
        if container is None:
            return
        unmodeled_fields(container, {"dependency"}, "maven-dependencies-fields-not-modeled")
        for dependency in children(container, "dependency"):
            group_id, artifact_id = scalar(dependency, "groupId"), scalar(dependency, "artifactId")
            if group_id is None or artifact_id is None:
                raise ValueError("Maven dependency coordinates require groupId and artifactId")
            optional = scalar(dependency, "optional", "false")
            if optional not in {"true", "false"}:
                raise ValueError("Maven optional must be true or false")
            exclusions = child(dependency, "exclusions")
            excluded = []
            if exclusions is not None:
                unmodeled_fields(exclusions, {"exclusion"}, "maven-exclusions-fields-not-modeled")
            for exclusion in children(exclusions, "exclusion") if exclusions is not None else []:
                excluded_group, excluded_artifact = scalar(exclusion, "groupId"), scalar(exclusion, "artifactId")
                if excluded_group is None or excluded_artifact is None:
                    raise ValueError("Maven exclusion requires exact group and artifact declarations")
                excluded.append({"group_id": excluded_group, "artifact_id": excluded_artifact})
                unmodeled_fields(exclusion, {"groupId", "artifactId"}, "maven-exclusion-fields-not-modeled")
            attributes = {
                "group_id": group_id, "artifact_id": artifact_id,
                "requested_spec": scalar(dependency, "version"), "scope": scalar(dependency, "scope", "compile"),
                "type": scalar(dependency, "type", "jar"), "classifier": scalar(dependency, "classifier"),
                "optional": optional == "true", "exclusions": excluded,
                "system_path": scalar(dependency, "systemPath"), "managed": managed,
                "resolution_status": "NOT_RUN",
            }
            if attributes["scope"] not in {"compile", "provided", "runtime", "test", "system", "import"}:
                raise ValueError("unsupported Maven dependency scope")
            if attributes["scope"] == "import" and (not managed or attributes["type"] != "pom"):
                raise ValueError("Maven import requires dependencyManagement and type pom")
            if (attributes["scope"] == "system") != (attributes["system_path"] is not None):
                raise ValueError("Maven system scope requires exactly a declared systemPath")
            ref = source(dependency)
            node = graph.node(NodeKind.DEPENDENCY, "maven", f"{group_id}:{artifact_id}", attributes, ref)
            graph.edge(declared_by, node, EdgeKind.MANAGES if managed else EdgeKind.DEPENDS, ref, condition)
            unmodeled_fields(dependency, {"groupId", "artifactId", "version", "scope", "type", "classifier", "optional", "exclusions", "systemPath"}, "maven-dependency-fields-not-modeled")
            if any(isinstance(value, str) and "${" in value for value in attributes.values()):
                graph.diagnostic("maven-property-expression-not-expanded", ref, "declaration retained verbatim")

    def plugins(container: ET.Element | None, declared_by: str, condition: str, managed: bool = False) -> None:
        if container is None:
            return
        unmodeled_fields(container, {"plugin"}, "maven-plugins-fields-not-modeled")
        for plugin in children(container, "plugin"):
            group_id = scalar(plugin, "groupId", "org.apache.maven.plugins")
            artifact_id = scalar(plugin, "artifactId")
            if artifact_id is None:
                raise ValueError("Maven plugin artifactId is required")
            ref = source(plugin)
            configuration = child(plugin, "configuration")
            node = graph.node(NodeKind.PLUGIN, "maven", f"{group_id}:{artifact_id}", {
                "version": scalar(plugin, "version"), "managed": managed,
                "configuration_digest": None if configuration is None else digest_bytes(ET.tostring(configuration)),
                "execution_status": "NOT_RUN",
            }, ref)
            graph.edge(declared_by, node, EdgeKind.MANAGES_PLUGIN if managed else EdgeKind.PLUGIN, ref, condition)
            unmodeled_fields(plugin, {"groupId", "artifactId", "version", "configuration", "dependencies", "executions"}, "maven-plugin-fields-not-modeled")
            dependencies(child(plugin, "dependencies"), node, condition)
            executions = child(plugin, "executions")
            if executions is not None:
                unmodeled_fields(executions, {"execution"}, "maven-executions-fields-not-modeled")
            seen: set[str] = set()
            for index, execution in enumerate(children(executions, "execution") if executions is not None else []):
                identity = scalar(execution, "id", f"declaration-{index}")
                assert identity is not None
                if identity in seen:
                    raise ValueError("duplicate Maven plugin execution id")
                seen.add(identity)
                goals = child(execution, "goals")
                goal_names = []
                if goals is not None:
                    unmodeled_fields(goals, {"goal"}, "maven-goals-fields-not-modeled")
                for goal in children(goals, "goal") if goals is not None else []:
                    if len(goal):
                        raise ValueError("Maven goal contains nested elements")
                    goal_names.append(_text((goal.text or "").strip(), "goal"))
                execution_ref = source(execution)
                execution_node = graph.node(NodeKind.EXECUTION, "maven", identity, {
                    "phase": scalar(execution, "phase"), "goals": goal_names,
                    "execution_status": "NOT_RUN", "declaration_digest": digest_bytes(ET.tostring(execution)),
                }, execution_ref)
                graph.edge(node, execution_node, EdgeKind.EXECUTION, execution_ref, condition)
                unmodeled_fields(execution, {"id", "phase", "goals", "configuration"}, "maven-execution-fields-not-modeled")

    def declarations(element: ET.Element, declared_by: str, condition: str) -> None:
        dependencies(child(element, "dependencies"), declared_by, condition)
        management = child(element, "dependencyManagement")
        if management is not None:
            unmodeled_fields(management, {"dependencies"}, "maven-dependency-management-fields-not-modeled")
            dependencies(child(management, "dependencies"), declared_by, condition, True)
        modules = child(element, "modules")
        if modules is not None:
            unmodeled_fields(modules, {"module"}, "maven-modules-fields-not-modeled")
        for module in children(modules, "module") if modules is not None else []:
            if len(module):
                raise ValueError("Maven module contains nested elements")
            graph.module_reference(declared_by, _text((module.text or "").strip(), "module"), source(module), condition, "pom.xml")
        properties = child(element, "properties")
        if properties is not None:
            seen_properties: set[str] = set()
            for prop in properties:
                key = prop.tag.removeprefix(namespace)
                if key in seen_properties or len(prop):
                    raise ValueError("duplicate or structured Maven property")
                seen_properties.add(key)
                ref = source(prop)
                node = graph.node(NodeKind.PROPERTY, "maven", key, {"literal_value": prop.text or "", "evaluation": "NOT_RUN"}, ref)
                graph.edge(declared_by, node, EdgeKind.CONTAINS, ref, condition)
        build = child(element, "build")
        if build is not None:
            plugins(child(build, "plugins"), declared_by, condition)
            management = child(build, "pluginManagement")
            if management is not None:
                unmodeled_fields(management, {"plugins"}, "maven-plugin-management-fields-not-modeled")
                plugins(child(management, "plugins"), declared_by, condition, True)
            unmodeled = sorted({item.tag.removeprefix(namespace) for item in build} - {"plugins", "pluginManagement"})
            if unmodeled:
                graph.diagnostic("maven-build-fields-not-semantically-modeled", source(build), unmodeled)

    declarations(root, owner, "always")
    profiles = child(root, "profiles")
    if profiles is not None:
        unmodeled_fields(profiles, {"profile"}, "maven-profiles-fields-not-modeled")
    seen_profiles: set[str] = set()
    for profile in children(profiles, "profile") if profiles is not None else []:
        identity = scalar(profile, "id")
        if identity is None or identity in seen_profiles:
            raise ValueError("Maven profile requires a unique id")
        seen_profiles.add(identity)
        activation = child(profile, "activation")
        ref = source(profile)
        node = graph.node(NodeKind.PROFILE, "maven", identity, {
            "requested_selection": identity in selected_profiles, "native_activation": "NOT_RUN",
            "activation_digest": None if activation is None else digest_bytes(ET.tostring(activation)),
        }, ref)
        graph.edge(owner, node, EdgeKind.CONTAINS, ref)
        declarations(profile, node, f"profile:{identity}")
        unmodeled_fields(profile, {"id", "activation", "dependencies", "dependencyManagement", "modules", "properties", "build"}, "maven-profile-fields-not-modeled")
    modeled = {"modelVersion", "groupId", "artifactId", "version", "packaging", "parent", "dependencies", "dependencyManagement", "modules", "properties", "build", "profiles"}
    unmodeled = sorted({item.tag.removeprefix(namespace) for item in root} - modeled)
    if unmodeled:
        graph.diagnostic("maven-project-fields-not-semantically-modeled", source(root), unmodeled)


def _semantic_digest(record: Mapping[str, Any]) -> str:
    # Source provenance changes remain in the graph digest; this projection
    # compares declaration meaning without treating whitespace as a new dependency.
    source = _mapping(record["source"], "graph source")
    return canonical_digest({**record, "source": {key: value for key, value in source.items() if key != "content_digest"}})


def _diff(current: Mapping[str, Any], baseline: Any) -> Mapping[str, Any]:
    baseline = _mapping(baseline, "baseline")
    if baseline == {"status": "NOT_PROVIDED"}:
        return {"status": "NO_BASELINE", "comparison_scope": "declarations-only"}
    _exact_mapping(baseline, "baseline", {"status", "graph"})
    if baseline["status"] != "PROVIDED":
        raise ValueError("unsupported baseline status")
    previous = _exact_mapping(baseline["graph"], "baseline graph", {"schema_version", "scope", "nodes", "edges", "graph_digest"})
    if previous["schema_version"] != SCHEMA_VERSION:
        raise ValueError("unsupported baseline graph schema")
    for key in ("tenant_id", "project_id"):
        if _mapping(previous["scope"], "baseline scope").get(key) != current["scope"][key]:
            raise ValueError("baseline crosses authenticated tenant/project")
    if canonical_digest({key: value for key, value in previous.items() if key != "graph_digest"}) != previous["graph_digest"]:
        raise ValueError("baseline graph digest mismatch")
    for key in ("workspace_digest", "revision_set_id"):
        validate_digest(previous["scope"].get(key), f"baseline {key}")
    differences: dict[str, Any] = {"status": "COMPARED", "comparison_scope": "declarations-only"}
    previous_maps: dict[str, dict[str, Mapping[str, Any]]] = {}
    for collection in ("nodes", "edges"):
        rows = _sequence(previous[collection], f"baseline {collection}", minimum=0, maximum=1024)
        old: dict[str, Mapping[str, Any]] = {}
        expected_keys = set(BuildNode.__dataclass_fields__ if collection == "nodes" else BuildEdge.__dataclass_fields__)
        for raw in rows:
            row = _exact_mapping(raw, f"baseline {collection} record", expected_keys)
            identity = _text(row["id"], "baseline identity", maximum=80)
            if identity in old:
                raise ValueError("duplicate baseline graph identity")
            ref = _exact_mapping(row["source"], "baseline source", set(SourceRef.__dataclass_fields__))
            _path(ref["path"])
            validate_digest(ref["content_digest"], "baseline source content digest")
            if ref["locator_format"] not in {"json-pointer", "maven-element-path"} or not isinstance(ref["locator"], str):
                raise ValueError("baseline source locator is unsupported")
            if collection == "nodes":
                NodeKind(row["kind"])
                if row["ecosystem"] not in {"npm", "maven"}:
                    raise ValueError("baseline ecosystem is unsupported")
                _mapping(row["attributes"], "baseline node attributes")
            else:
                EdgeKind(row["kind"])
            old[identity] = row
        previous_maps[collection] = old
        new = {row["id"]: row for row in current[collection]}
        differences[collection] = {
            "added": sorted(set(new) - set(old)), "removed": sorted(set(old) - set(new)),
            "changed": sorted(key for key in set(old) & set(new) if _semantic_digest(old[key]) != _semantic_digest(new[key])),
        }
    for edge in previous_maps["edges"].values():
        if edge["source_node"] not in previous_maps["nodes"] or edge["target_node"] not in previous_maps["nodes"]:
            raise ValueError("baseline edge refers to a missing node")
    return differences


def _execute(skill: str, payload: Mapping[str, Any], scope: TenantScope, invocation: str) -> Mapping[str, Any]:
    if skill not in SKILLS:
        raise ValueError("unsupported exact build graph Skill")
    values = _exact_mapping(payload.get("inputs"), "inputs", set(INPUTS))
    canonical_value(values)
    artifact = _exact_mapping(values["normalized repository artifact"], "repository artifact", {
        "tenant_id", "project_id", "workspace_digest", "revision_set_id", "files",
    })
    for key in ("tenant_id", "project_id", "workspace_digest", "revision_set_id"):
        if artifact[key] != getattr(scope, key):
            raise ValueError(f"repository artifact {key} differs from authenticated scope")
    for field, key in (("runtime trace", "records"), ("test result", "cases")):
        record = _exact_mapping(values[field], field, {"status", key})
        if record != {"status": "NOT_RUN", key: []}:
            raise ValueError(f"{field} cannot manufacture native verification; only explicit NOT_RUN is supported")
    metadata = _exact_mapping(values["build metadata"], "build metadata", {"parser_profiles", "selected_maven_profiles", "baseline"})
    profiles = _mapping(metadata["parser_profiles"], "parser_profiles")
    selected_profiles = set(_text_list(metadata["selected_maven_profiles"], "selected_maven_profiles", maximum=32))
    files: dict[str, tuple[str, str]] = {}
    for raw in _sequence(artifact["files"], "manifest files", maximum=32):
        file = _exact_mapping(raw, "manifest", {"path", "content", "content_digest"})
        path = _path(file["path"])
        if path in files:
            raise ValueError("duplicate manifest path")
        content = _text(file["content"], "manifest content", maximum=65_536)
        digest = digest_bytes(content.encode("utf-8"))
        if digest != file["content_digest"]:
            raise ValueError("manifest content digest mismatch")
        profile = profiles.get(path)
        if not isinstance(profile, str) or profile not in PROFILES or PurePosixPath(path).name != PROFILES[profile]:
            raise ValueError("unsupported manifest path/parser profile; only Maven4.0.0 POM and npm10 package.json are supported")
        files[path] = (content, digest)
    if set(profiles) != set(files):
        raise ValueError("parser profiles must cover the exact supplied manifest inventory")
    graph = _Graph({key: artifact[key] for key in ("tenant_id", "project_id", "workspace_digest", "revision_set_id")})
    for path, (content, digest) in sorted(files.items()):
        if profiles[path] == "maven-pom-4.0.0":
            _maven(graph, path, content, digest, selected_profiles)
        else:
            _npm(graph, path, content, digest)
    result = graph.finish()
    known_profiles = {node.name for node in graph.nodes.values() if node.kind == NodeKind.PROFILE}
    missing_profiles = sorted(selected_profiles - known_profiles)
    return _response({
        "semantic graph": result,
        "architecture model": {
            "module_paths": sorted(graph.modules),
            "node_kind_counts": dict(sorted(Counter(node.kind for node in graph.nodes.values()).items())),
            "edge_kind_counts": dict(sorted(Counter(edge.kind for edge in graph.edges.values()).items())),
            "inventory_scope": "supplied-manifests-only",
        },
        "semantic diff": _diff(result, metadata["baseline"]),
        "confidence report": {
            "parsed_manifest_count": len(files), "supplied_manifest_count": len(files),
            "local_graph_consistent": True, "whole_repository_complete": False,
            "supported_parser_profiles": sorted(PROFILES),
            "unsupported": ["Maven effective inheritance/property expansion/profile activation", "transitive dependency/version resolution",
                            "Gradle/Python/Cargo/lockfile semantics", "lifecycle/plugin/code-generation execution"],
            "diagnostics": sorted(graph.diagnostics, key=lambda row: canonical_digest(row)),
            "requested_profiles_not_declared": missing_profiles,
            "source_provenance": "CALLER_SUPPLIED_CONTENT_DIGEST_CHECKED",
            "input_digest": canonical_digest(values), "native_build_status": "NOT_RUN",
            "native_test_status": "NOT_RUN", "provider_execution_status": "NOT_RUN",
            "independent_verification": "NOT_RUN", "certification_status": "NOT_CERTIFIED",
        },
    })


def build_build_graph_handlers(catalog: CatalogView, store: FoundryStore | None) -> dict[str, LocalHandler]:
    if not SKILLS.issubset(catalog.atomic_skills):
        raise ValueError("exact build-and-dependency-graph contract is absent")
    return {"build-and-dependency-graph": _execute}
