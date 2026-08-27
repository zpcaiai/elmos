"""Static legacy Java Web forensics and semantic IR projection.

The front-end consumes only the immutable snapshot.  XML is parsed structurally;
Java extraction is deliberately conservative and records unknowns instead of
guessing through a permissive template or regex-only converter.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import hashlib
import re
from typing import Any, Iterable
import xml.etree.ElementTree as ET

from .canonical import canonical_digest
from .snapshot import RepositorySnapshot, SnapshotFile


@dataclass(frozen=True, slots=True)
class Evidence:
    ref: str
    kind: str
    uri: str
    digest: str
    line_start: int | None = None

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {"kind": self.kind, "uri": self.uri, "digest": self.digest}
        if self.line_start is not None:
            value["lineStart"] = self.line_start
            value["lineEnd"] = self.line_start
        value.update({"environment": "static-snapshot", "extractor": "elmos-legacy-web-static", "extractorVersion": "1.0.0"})
        return value


@dataclass(frozen=True, slots=True)
class ForensicModel:
    modules: tuple[dict[str, Any], ...]
    framework_inventory: tuple[dict[str, Any], ...]
    runtime_topology: dict[str, Any]
    routes: tuple[dict[str, Any], ...]
    config_overlays: tuple[dict[str, Any], ...]
    dependencies: tuple[dict[str, Any], ...]
    recovery: dict[str, Any]
    ir: dict[str, Any]
    graph: dict[str, Any]
    unknowns: tuple[dict[str, Any], ...]


def _line_of(text: str, position: int) -> int:
    return text.count("\n", 0, position) + 1


def _evidence(file: SnapshotFile, *, kind: str = "source", line: int | None = None, suffix: str = "") -> Evidence:
    path_digest = file.digest.removeprefix("sha256:")[:16]
    ref = f"ev:{path_digest}:{file.path}:{line or 1}{suffix}"
    return Evidence(ref=ref, kind=kind, uri=f"snapshot://{file.path}", digest=file.digest, line_start=line)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _xml_root(file: SnapshotFile) -> ET.Element | None:
    if file.text is None:
        return None
    try:
        return ET.fromstring(file.text)
    except ET.ParseError:
        return None


def _iter_xml(root: ET.Element, name: str) -> Iterable[ET.Element]:
    return (item for item in root.iter() if _local_name(item.tag) == name)


def _module_id(path: str) -> str:
    return "module:" + (path.removesuffix("/pom.xml").replace("/", ":") or "root")


def _parse_modules(snapshot: RepositorySnapshot) -> tuple[dict[str, Any], ...]:
    result: list[dict[str, Any]] = []
    pom_files = [item for item in snapshot.files if item.path.endswith("pom.xml") and item.kind == "file"]
    for file in pom_files:
        root = _xml_root(file)
        artifact_id = None
        packaging = "unknown"
        dependencies: list[str] = []
        child_modules: list[str] = []
        if root is not None:
            for item in _iter_xml(root, "artifactId"):
                if item.text and item.text.strip():
                    artifact_id = item.text.strip()
                    break
            packaging_node = next(iter(_iter_xml(root, "packaging")), None)
            if packaging_node is not None and packaging_node.text:
                packaging = packaging_node.text.strip()
            for item in _iter_xml(root, "dependency"):
                group = next((x.text.strip() for x in item if _local_name(x.tag) == "groupId" and x.text), "")
                artifact = next((x.text.strip() for x in item if _local_name(x.tag) == "artifactId" and x.text), "")
                if group and artifact:
                    dependencies.append(f"{group}:{artifact}")
            for item in _iter_xml(root, "module"):
                if item.text and item.text.strip():
                    child_modules.append(item.text.strip())
        if packaging not in {"jar", "war", "ear"}:
            packaging = "war" if any(v.path.endswith(".jsp") for v in snapshot.files) else "jar"
        result.append({
            "id": _module_id(file.path),
            "name": artifact_id or file.path.removesuffix("/pom.xml") or "root",
            "packaging": packaging,
            "frameworks": [],
            "dependsOn": dependencies,
            "childModules": child_modules,
            "evidenceRefs": [_evidence(file, kind="build").ref],
        })
    if not result:
        web = any(item.path.endswith(("web.xml", ".jsp")) for item in snapshot.files)
        result.append({
            "id": "module:repository",
            "name": "repository",
            "packaging": "war" if web else "unknown",
            "frameworks": [],
            "dependsOn": [],
            "evidenceRefs": [f"ev:snapshot:{snapshot.digest}"],
        })
    return tuple(result)


def _frameworks(snapshot: RepositorySnapshot) -> tuple[dict[str, Any], ...]:
    text = "\n".join(item.text or "" for item in snapshot.files if item.kind == "file")
    findings: list[dict[str, Any]] = []
    signatures = (
        ("struts1", ("org.apache.struts.action.Action", "struts-config", "org.apache.struts:struts-core")),
        ("struts2", ("com.opensymphony.xwork", "struts-default", "org.apache.struts:struts2-core")),
        ("servlet", ("javax.servlet", "jakarta.servlet", "<servlet>", "@WebServlet")),
        ("jsp", (".jsp", "taglib", "JSTL", "javax.servlet.jsp")),
        ("spring", ("org.springframework", "@Controller", "@RequestMapping")),
    )
    for name, needles in signatures:
        hits = sum(text.count(needle) for needle in needles)
        if hits:
            evidence_file = next((item for item in snapshot.files if any(needle in (item.text or "") for needle in needles)), snapshot.files[0] if snapshot.files else None)
            findings.append({
                "id": f"framework:{name}",
                "name": name,
                "version": "unknown",
                "evidenceCount": hits,
                "confidence": 0.75 if name in {"struts1", "struts2"} else 0.65,
                "evidenceRefs": [_evidence(evidence_file, kind="source").ref] if evidence_file else ["ev:no-files"],
            })
    return tuple(findings)


def _path_pattern(value: str | None, *, suffix: str = "") -> str:
    if not value:
        return "/unknown"
    value = value.strip()
    if not value.startswith("/"):
        value = "/" + value
    if suffix and not value.endswith(suffix):
        value += suffix
    return value


def _routes(snapshot: RepositorySnapshot) -> tuple[dict[str, Any], ...]:
    found: list[dict[str, Any]] = []
    for file in snapshot.files:
        if file.kind != "file" or file.text is None:
            continue
        root = _xml_root(file) if file.path.endswith((".xml", ".tld")) else None
        if root is not None and ("struts-config" in file.path or "struts" in (file.text or "").lower()):
            for action in _iter_xml(root, "action"):
                path = action.attrib.get("path") or action.attrib.get("name")
                owner = action.attrib.get("type") or action.attrib.get("class") or "unknown.Action"
                if not path:
                    continue
                navigation = []
                for forward in list(action):
                    if _local_name(forward.tag) == "forward" and forward.attrib.get("path"):
                        navigation.append({"when": forward.attrib.get("name", "SUCCESS"), "kind": "forward", "target": forward.attrib["path"], "status": 200, "preserveRequestAttributes": True})
                if not navigation:
                    navigation = [{"when": "SUCCESS", "kind": "render", "target": None, "status": 200, "preserveRequestAttributes": True}]
                framework = "struts1" if "struts-config" in file.path or owner.endswith("Action") else "struts2"
                found.append(_route(path, framework, owner, file, navigation, suffix=""))
            for action in _iter_xml(root, "action"):
                if action.attrib.get("name") and action.attrib.get("class") and "struts-config" not in file.path:
                    path = "/" + action.attrib["name"] + ".action"
                    navigation = []
                    for result in _iter_xml(action, "result"):
                        navigation.append({"when": result.attrib.get("name", "success"), "kind": "render", "target": (result.text or "").strip() or None, "status": 200, "preserveRequestAttributes": True})
                    found.append(_route(path, "struts2", action.attrib["class"], file, navigation or [{"when": "success", "kind": "render", "target": None, "status": 200, "preserveRequestAttributes": True}]))
        if root is not None and file.path.endswith("web.xml"):
            for mapping in _iter_xml(root, "servlet-mapping"):
                servlet_name = next((child.text.strip() for child in mapping if _local_name(child.tag) == "servlet-name" and child.text), "unknown")
                pattern = next((child.text.strip() for child in mapping if _local_name(child.tag) == "url-pattern" and child.text), None)
                if pattern:
                    found.append(_route(pattern, "servlet", servlet_name, file, [{"when": "REQUEST", "kind": "render", "target": None, "status": 200, "preserveRequestAttributes": True}]))
    # Annotation extraction is symbol-aware enough to bind the route to the
    # nearest class, but intentionally leaves composed annotations unknown.
    for file in snapshot.files:
        if file.kind != "file" or file.text is None or not file.path.endswith(".java"):
            continue
        for match in re.finditer(r"@(RequestMapping|GetMapping|PostMapping)\s*(?:\(([^)]*)\))?", file.text):
            args = match.group(2) or ""
            path_match = re.search(r"(?:value|path)\s*=\s*\"([^\"]+)\"|\"([^\"]+)\"", args)
            path = (path_match.group(1) or path_match.group(2)) if path_match else None
            if not path:
                continue
            method = "POST" if match.group(1) == "PostMapping" else "GET" if match.group(1) == "GetMapping" else "GET"
            owner_match = re.search(r"(?:public\s+)?class\s+([A-Za-z0-9_$]+)", file.text[match.end():])
            owner = owner_match.group(1) if owner_match else "unknown.Controller"
            found.append(_route(path, "spring", owner, file, [{"when": "SUCCESS", "kind": "render", "target": None, "status": 200, "preserveRequestAttributes": True}], methods=(method,), line=_line_of(file.text, match.start())))
    dedup: dict[tuple[str, tuple[str, ...], str], dict[str, Any]] = {}
    for route in found:
        key = (route["pathPattern"], tuple(route["methods"]), route["owner"]["symbol"])
        dedup[key] = route
    return tuple(sorted(dedup.values(), key=lambda item: (item["pathPattern"], item["owner"]["symbol"])))


def _route(path: str, framework: str, owner: str, file: SnapshotFile, navigation: list[dict[str, Any]], *, suffix: str = "", methods: tuple[str, ...] = ("GET", "POST"), line: int | None = None) -> dict[str, Any]:
    path = _path_pattern(path, suffix=suffix)
    route_key = hashlib.sha256(f"{methods}:{path}:{owner}".encode()).hexdigest()[:16]
    return {
        "id": f"endpoint:{route_key}",
        "pathPattern": path,
        "methods": list(methods),
        "dispatcherTypes": ["REQUEST"],
        "owner": {"framework": framework, "symbol": owner},
        "pipelineId": f"pipeline:{route_key}",
        "bindingIds": [], "stateReadIds": [], "stateWriteIds": [], "securityRuleIds": [], "transactionIds": [], "sideEffectIds": [],
        "navigation": navigation,
        "criticality": "high" if framework in {"struts1", "struts2", "servlet"} else "medium",
        "evidenceRefs": [_evidence(file, kind="config" if file.path.endswith(".xml") else "source", line=line).ref],
    }


def _config_overlays(snapshot: RepositorySnapshot) -> tuple[dict[str, Any], ...]:
    overlays: list[dict[str, Any]] = []
    for file in snapshot.files:
        name = file.path.rsplit("/", 1)[-1]
        if name.startswith(("application", "bootstrap", "web")) and name.endswith((".properties", ".yaml", ".yml", ".xml")):
            secret_keys: list[str] = []
            if file.text:
                for line in file.text.splitlines():
                    if re.search(r"(?i)(password|secret|token|api[_-]?key|credential)", line):
                        key = line.split("=", 1)[0].split(":", 1)[0].strip()
                        if key and key not in secret_keys:
                            secret_keys.append(key)
            overlays.append({"path": file.path, "profile": _profile_from_name(name), "secretReferences": secret_keys, "evidenceRefs": [_evidence(file, kind="config").ref]})
    return tuple(overlays)


def _profile_from_name(name: str) -> str:
    match = re.search(r"-(dev|test|staging|prod|production|local)", name)
    return match.group(1) if match else "default"


def _dependencies(snapshot: RepositorySnapshot, frameworks: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    values: list[dict[str, Any]] = []
    for file in snapshot.files:
        if file.kind != "file" or file.text is None:
            continue
        if file.path.endswith("pom.xml"):
            root = _xml_root(file)
            if root is None:
                continue
            for dependency in _iter_xml(root, "dependency"):
                group = next((x.text.strip() for x in dependency if _local_name(x.tag) == "groupId" and x.text), "")
                artifact = next((x.text.strip() for x in dependency if _local_name(x.tag) == "artifactId" and x.text), "")
                version = next((x.text.strip() for x in dependency if _local_name(x.tag) == "version" and x.text), "managed-or-unknown")
                if group and artifact:
                    values.append({"coordinate": f"{group}:{artifact}", "version": version, "namespace": "javax" if "javax" in group else "jakarta" if "jakarta" in group else "neutral", "risk": "critical" if "struts" in artifact or "ognl" in artifact else "high" if "javax" in group else "medium", "evidenceRefs": [_evidence(file, kind="build").ref]})
        elif file.path.endswith(("build.gradle", "build.gradle.kts")):
            for match in re.finditer(r"(?:implementation|compile|api)\s*[('\\\"]([^'\\\"]+)", file.text):
                values.append({"coordinate": match.group(1), "version": "declared-or-managed", "namespace": "javax" if "javax" in match.group(1) else "neutral", "risk": "medium", "evidenceRefs": [_evidence(file, kind="build", line=_line_of(file.text, match.start())).ref]})
    if any(item["name"] == "struts1" for item in frameworks):
        values.append({"coordinate": "org.apache.struts:struts-core", "version": "detected", "namespace": "javax", "risk": "critical", "evidenceRefs": [item["evidenceRefs"][0] for item in frameworks if item["name"] == "struts1"]})
    return tuple({(item["coordinate"], item["version"]): item for item in values}.values())


def _state_and_effects(snapshot: RepositorySnapshot) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    states: dict[str, dict[str, Any]] = {}
    effects: list[dict[str, Any]] = []
    transactions: list[dict[str, Any]] = []
    security: list[dict[str, Any]] = []
    for file in snapshot.files:
        if file.kind != "file" or file.text is None:
            continue
        text = file.text
        ev = _evidence(file, kind="source")
        for match in re.finditer(r"(?:getSession\(\)|session)\.(?:setAttribute|put)\s*\(\s*[\"']([^\"']+)", text):
            key = match.group(1)
            state = states.setdefault(key, {"id": f"state:{key}", "key": key, "scope": "session", "type": "unknown", "lifetime": "session", "serializable": None, "reads": [], "writes": [], "evidenceRefs": []})
            state["writes"].append(f"symbol:{file.path}"); state["evidenceRefs"].append(ev.ref)
        for match in re.finditer(r"(?:getSession\(\)|session)\.(?:getAttribute|get)\s*\(\s*[\"']([^\"']+)", text):
            key = match.group(1)
            state = states.setdefault(key, {"id": f"state:{key}", "key": key, "scope": "session", "type": "unknown", "lifetime": "session", "serializable": None, "reads": [], "writes": [], "evidenceRefs": []})
            state["reads"].append(f"symbol:{file.path}"); state["evidenceRefs"].append(ev.ref)
        for match in re.finditer(r"(?:getParameter|getParameterValues)\s*\(\s*[\"']([^\"']+)", text):
            key = match.group(1)
            states.setdefault(f"request:{key}", {"id": f"state:request:{key}", "key": key, "scope": "request", "type": "String", "lifetime": "request", "serializable": True, "reads": [f"symbol:{file.path}"], "writes": [], "evidenceRefs": [ev.ref]})
        for index, match in enumerate(re.finditer(r"(?i)\b(insert|update|delete|select)\b[^;\n]*", text)):
            operation = match.group(1).lower()
            effects.append({"id": f"effect:{hashlib.sha256((file.path + str(match.start())).encode()).hexdigest()[:16]}", "kind": "database", "destination": "sql-sink", "operation": operation, "order": index + 1, "idempotency": "unknown", "transactionId": None, "evidenceRefs": [ev.ref]})
        if re.search(r"@Transactional|beginTransaction|\.commit\s*\(|\.rollback\s*\(", text):
            transactions.append({"id": f"tx:{hashlib.sha256(file.path.encode()).hexdigest()[:16]}", "boundary": file.path, "propagation": "unknown", "isolation": "unknown", "commit": "observed-or-annotation", "rollback": "observed-or-unknown", "evidenceRefs": [ev.ref]})
        if re.search(r"(?i)csrf|csrfToken|tokenInterceptor|security-constraint|auth-constraint|roles-allowed|isUserInRole", text):
            security.append({"id": f"security:{hashlib.sha256(file.path.encode()).hexdigest()[:16]}", "kind": "authentication-or-csrf", "decisionPoint": "before-action", "roles": [], "onDeny": {"kind": "unknown", "target": None}, "evidenceRefs": [ev.ref]})
        for match in re.finditer(r"(?i)(JMS|Kafka|HttpClient|RestTemplate|send\s*\(|FileOutputStream|JavaMail|WebSocket)", text):
            effects.append({"id": f"effect:{hashlib.sha256((file.path + str(match.start())).encode()).hexdigest()[:16]}", "kind": "external", "destination": match.group(1), "operation": "invoke", "order": len(effects) + 1, "idempotency": "unknown", "transactionId": None, "evidenceRefs": [ev.ref]})
    return list(states.values()), effects, transactions, security


def _unknowns(snapshot: RepositorySnapshot, config_overlays: tuple[dict[str, Any], ...], routes: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    result: list[dict[str, Any]] = []
    for file in snapshot.files:
        if file.kind != "file" or file.text is None:
            continue
        patterns = (
            (r"Class\.forName|Method\.invoke|ServiceLoader", "dynamic-reflection", "high", "reflection-driven behavior cannot be resolved statically"),
            (r"OGNL|ValueStack|\$\{[^}]+\}", "dynamic-reflection", "high", "dynamic expression access requires runtime evidence"),
            (r"Runtime\.getRuntime|ProcessBuilder|System\.getenv", "missing-environment", "high", "environment-dependent behavior is not available in static mode"),
            (r"Cipher|getDecrypted|decrypt", "encrypted-config", "high", "encrypted configuration cannot be interpreted without an approved key boundary"),
        )
        for pattern, category, severity, description in patterns:
            if re.search(pattern, file.text):
                result.append({"id": f"UNK-{hashlib.sha256((file.path + category).encode()).hexdigest()[:12].upper()}", "category": category, "severity": severity, "status": "open", "scope": {"path": file.path}, "description": description, "evidenceRefs": [_evidence(file).ref], "resolutionPlan": ["collect approved runtime trace", "bind result to an isolated environment"], "blocks": ["E4", "E5"] if severity == "high" else ["E5"]})
    if not routes:
        result.append({"id": "UNK-NO-ROUTES", "category": "unreplayed-path", "severity": "critical", "status": "open", "scope": {}, "description": "no effective route was statically recovered", "evidenceRefs": [f"ev:snapshot:{snapshot.digest}"], "resolutionPlan": ["provide an approved runtime route inventory"], "blocks": ["E1", "E4", "E5"]})
    for overlay in config_overlays:
        if overlay["secretReferences"]:
            result.append({"id": f"UNK-CONFIG-{hashlib.sha256(overlay['path'].encode()).hexdigest()[:10].upper()}", "category": "missing-environment", "severity": "high", "status": "open", "scope": {"path": overlay["path"], "profile": overlay["profile"]}, "description": "secret references are present but their values are intentionally unavailable", "evidenceRefs": list(overlay["evidenceRefs"]), "resolutionPlan": ["resolve a secret reference through an environment-owned authority"], "blocks": ["E4", "E5"]})
    return tuple(result)


def _pipelines(routes: tuple[dict[str, Any], ...], frameworks: tuple[dict[str, Any], ...], files: tuple[SnapshotFile, ...]) -> tuple[dict[str, Any], ...]:
    framework_names = {item["name"] for item in frameworks}
    result: list[dict[str, Any]] = []
    for route in routes:
        steps: list[dict[str, Any]] = []
        order = 100
        if "struts1" in framework_names:
            for kind in ("form-reset", "populate", "validation"):
                steps.append({"id": f"{route['pipelineId']}:{kind}", "kind": kind, "order": order, "phase": "before", "condition": None, "shortCircuit": {"onFailure": "input"} if kind == "validation" else {}, "reads": [], "writes": [], "sideEffects": [], "evidenceRefs": list(route["evidenceRefs"])}); order += 100
        if "struts2" in framework_names:
            steps.append({"id": f"{route['pipelineId']}:interceptors", "kind": "interceptor-stack", "order": order, "phase": "before", "condition": None, "shortCircuit": {"onDeny": "error"}, "reads": [], "writes": [], "sideEffects": [], "evidenceRefs": list(route["evidenceRefs"])}); order += 100
        steps.append({"id": f"{route['pipelineId']}:action", "kind": "action", "order": order, "phase": "invoke", "condition": None, "shortCircuit": {}, "reads": [], "writes": [], "sideEffects": [], "evidenceRefs": list(route["evidenceRefs"])}); order += 100
        steps.append({"id": f"{route['pipelineId']}:navigation", "kind": "navigation", "order": order, "phase": "result", "condition": None, "shortCircuit": {}, "reads": [], "writes": [], "sideEffects": [], "evidenceRefs": list(route["evidenceRefs"])});
        result.append({"id": route["pipelineId"], "steps": steps, "evidenceRefs": list(route["evidenceRefs"])})
    return tuple(result)


def build_forensic_model(snapshot: RepositorySnapshot) -> ForensicModel:
    modules = _parse_modules(snapshot)
    frameworks = _frameworks(snapshot)
    routes = _routes(snapshot)
    overlays = _config_overlays(snapshot)
    dependencies = _dependencies(snapshot, frameworks)
    states, effects, transactions, security = _state_and_effects(snapshot)
    pipelines = _pipelines(routes, frameworks, snapshot.files)
    unknowns = _unknowns(snapshot, overlays, routes)
    framework_names = [item["name"] for item in frameworks]
    for module in modules:
        module["frameworks"] = framework_names
    for route in routes:
        route["bindingIds"] = [state["id"].replace("state:request:", "binding:") for state in states if state["scope"] == "request"]
        route["stateReadIds"] = [state["id"] for state in states if route["owner"]["symbol"].split(".")[-1] in " ".join(state["reads"])]
        route["stateWriteIds"] = [state["id"] for state in states if route["owner"]["symbol"].split(".")[-1] in " ".join(state["writes"])]
        route["securityRuleIds"] = [rule["id"] for rule in security]
        route["transactionIds"] = [item["id"] for item in transactions]
        route["sideEffectIds"] = [item["id"] for item in effects]
    ir = {
        "irVersion": "1.0.0",
        "repositorySnapshotId": snapshot.digest,
        "targetBaselineHint": {"springBoot": "4.x", "springFramework": "7.x", "jakartaEE": "11", "servlet": "6.1", "java": 21},
        "modules": list(modules), "endpoints": list(routes), "pipelines": list(pipelines),
        "bindings": [{"id": state["id"].replace("state:request:", "binding:"), "sourceName": state["key"], "aliases": [], "targetPath": state["key"], "targetType": state["type"], "scope": state["scope"], "required": False, "resetBeforePopulate": False, "conversion": {"kind": "string", "onError": "validation"}, "allowlisted": True, "evidenceRefs": state["evidenceRefs"]} for state in states if state["scope"] == "request"],
        "stateObjects": states,
        "views": [{"id": f"view:{hashlib.sha256(file.path.encode()).hexdigest()[:16]}", "kind": "jsp", "path": "/" + file.path, "reads": [], "taglibs": sorted(set(re.findall(r"taglib\s+prefix\s*=\s*\"[^\"]+\"\s+uri\s*=\s*\"([^\"]+)", file.text or ""))), "sideEffects": [], "evidenceRefs": [_evidence(file, kind="source").ref]} for file in snapshot.files if file.kind == "file" and file.path.endswith(".jsp")],
        "securityRules": security,
        "transactions": transactions,
        "sideEffects": effects,
        "deployment": {"contextPath": "unknown", "packaging": modules[0]["packaging"], "webInfProtected": True, "runtime": "unknown"},
        "concurrency": [{"id": f"concurrency:{hashlib.sha256(file.path.encode()).hexdigest()[:12]}", "path": file.path, "threadLocal": "ThreadLocal" in (file.text or ""), "singletonMutableState": bool(re.search(r"static\s+(?:final\s+)?(?:Map|List|Set|[A-Za-z0-9_$]+)\s+[A-Za-z0-9_$]+", file.text or "")), "evidenceRefs": [_evidence(file).ref]} for file in snapshot.files if file.kind == "file" and file.path.endswith(".java") and re.search(r"ThreadLocal|static\s+", file.text or "")],
        "unknownRefs": [item["id"] for item in unknowns],
        "evidenceCoverage": {"totalNodes": len(routes) + len(states) + len(effects) + len(modules), "confirmed": len(routes) + len(states) + len(effects) + len(modules), "inferred": len(unknowns), "unknown": len(unknowns)},
    }
    graph = build_evidence_graph(snapshot, ir, frameworks, overlays, dependencies, unknowns)
    runtime_topology = {"packaging": modules[0]["packaging"], "containers": ["unknown"], "contextPath": "unknown", "jndi": any("jndi" in (file.text or "").lower() for file in snapshot.files), "servletApi": "unknown", "evidenceRefs": [f"ev:snapshot:{snapshot.digest}"]}
    recovery = {"struts1": [route["id"] for route in routes if route["owner"]["framework"] == "struts1"], "struts2": [route["id"] for route in routes if route["owner"]["framework"] == "struts2"], "servlet": [route["id"] for route in routes if route["owner"]["framework"] == "servlet"], "jsp": [view["id"] for view in ir["views"]]}
    return ForensicModel(modules=modules, framework_inventory=frameworks, runtime_topology=runtime_topology, routes=routes, config_overlays=overlays, dependencies=dependencies, recovery={"recovery": recovery, "pipelines": list(pipelines), "states": states, "transactions": transactions, "security": security, "effects": effects}, ir=ir, graph=graph, unknowns=unknowns)


def build_evidence_graph(snapshot: RepositorySnapshot, ir: dict[str, Any], frameworks: tuple[dict[str, Any], ...], overlays: tuple[dict[str, Any], ...], dependencies: tuple[dict[str, Any], ...], unknowns: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = [{"id": "repository:" + snapshot.digest.removeprefix("sha256:")[:16], "type": "repository", "label": snapshot.root_label, "status": "confirmed", "confidence": 1.0, "attributes": {"fileCount": len(snapshot.files)}, "evidence": [{"kind": "source", "uri": "snapshot://manifest", "digest": snapshot.digest, "environment": "static-snapshot", "extractor": "snapshot", "extractorVersion": "1.0.0"}]}]
    edges: list[dict[str, Any]] = []
    for item in snapshot.files:
        node_id = "file:" + hashlib.sha256(item.path.encode()).hexdigest()[:16]
        nodes.append({"id": node_id, "type": "file", "label": item.path, "status": "confirmed", "confidence": 1.0, "attributes": {"kind": item.kind, "bytes": item.size}, "evidence": [_evidence(item).to_dict()]})
        edges.append({"id": "edge:" + hashlib.sha256((nodes[0]["id"] + node_id).encode()).hexdigest()[:16], "from": nodes[0]["id"], "to": node_id, "type": "contains", "status": "confirmed", "confidence": 1.0, "attributes": {}})
    def add_node(item: dict[str, Any], node_type: str, label_key: str, status: str = "confirmed", confidence: float = 0.85) -> None:
        item_id = item["id"]
        refs = item.get("evidenceRefs", []) or [f"ev:snapshot:{snapshot.digest}"]
        nodes.append({"id": item_id, "type": node_type, "label": str(item.get(label_key, item_id)), "status": status, "confidence": confidence, "attributes": {key: value for key, value in item.items() if key not in {"id", label_key, "evidenceRefs"}}, "evidence": [{"kind": "source", "uri": f"evidence://{ref}", "digest": canonical_digest(ref), "environment": "static-snapshot", "extractor": "semantic-front-end", "extractorVersion": "1.0.0"} for ref in refs]})
    for module in ir["modules"]: add_node(module, "module", "name")
    for route in ir["endpoints"]: add_node(route, "route", "pathPattern")
    for state in ir["stateObjects"]: add_node(state, "state", "key")
    for view in ir["views"]: add_node(view, "view", "path")
    for unknown in unknowns: add_node(unknown, "unknown", "description", "unknown", 0.0)
    for route in ir["endpoints"]:
        for target in (route["pipelineId"], *route.get("stateReadIds", []), *route.get("stateWriteIds", []), *route.get("sideEffectIds", [])):
            if any(node["id"] == target for node in nodes):
                edges.append({"id": "edge:" + hashlib.sha256((route["id"] + target).encode()).hexdigest()[:16], "from": route["id"], "to": target, "type": "handles" if target == route["pipelineId"] else "writes", "status": "inferred", "confidence": 0.75, "attributes": {}})
    total = len(nodes)
    unknown_count = sum(node["status"] == "unknown" for node in nodes)
    return {"graphVersion": "1.0.0", "repositorySnapshotId": snapshot.digest, "environmentClass": "static-snapshot", "nodes": nodes, "edges": edges, "coverage": {"totalFacts": total, "confirmedFacts": total - unknown_count, "inferredFacts": 0, "unknownFacts": unknown_count}}
