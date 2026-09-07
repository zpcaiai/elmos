#!/usr/bin/env python3
"""Detect the runnable profile of an ELMOS-generated or converted project.

Emits `smoke/profile.json`: stacks, datastores, external dependencies, ports and
an explicit `unknown` list. Detection is evidence-bearing — every claim records
the file and marker it came from. Nothing is guessed silently; anything the
detector cannot resolve is written to `unknown` and blocks certification rather
than being filled in with a default.

Usage:
    python3 scripts/batch46/detect_project_profile.py <project-root> [--write]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from smoke_common import (
    SCHEMA_PREFIX,
    canonical_digest,
    file_digest,
    iter_files,
    read_text,
    rel,
    smoke_dir,
    utc_now,
    write_json,
)

PY_FRAMEWORKS = {
    "fastapi": {"port": 8000, "readiness": "/health", "family": "b30"},
    "flask": {"port": 5000, "readiness": "/health", "family": "b30"},
    "django": {"port": 8000, "readiness": "/health/", "family": "b30"},
    "starlette": {"port": 8000, "readiness": "/health", "family": "b30"},
}
NODE_FRAMEWORKS = {
    "@nestjs/core": {"name": "nestjs", "port": 3000, "readiness": "/health", "family": "b30"},
    "express": {"name": "express", "port": 3000, "readiness": "/health", "family": "b30"},
    "fastify": {"name": "fastify", "port": 3000, "readiness": "/health", "family": "b30"},
    "next": {"name": "next", "port": 3000, "readiness": "/", "family": "b32"},
    "react": {"name": "react", "port": 5173, "readiness": "/", "family": "b32"},
    "vue": {"name": "vue", "port": 5173, "readiness": "/", "family": "b32"},
    "@angular/core": {"name": "angular", "port": 4200, "readiness": "/", "family": "b32"},
    "svelte": {"name": "svelte", "port": 5173, "readiness": "/", "family": "b32"},
}
JAVA_FRAMEWORKS = {
    "spring-boot": {"port": 8080, "readiness": "/actuator/health", "family": "b30"},
    "quarkus": {"port": 8080, "readiness": "/q/health/ready", "family": "b30"},
    "micronaut": {"port": 8080, "readiness": "/health", "family": "b30"},
    "jakarta": {"port": 8080, "readiness": "/health", "family": "b30"},
}
DOTNET_FRAMEWORKS = {
    "Microsoft.NET.Sdk.Web": {"name": "aspnetcore", "port": 5000, "readiness": "/health", "family": "b30"},
}

DATASTORE_MARKERS = {
    "postgres": ("postgres", "postgresql", "npgsql", "psycopg", "pg8000", "jdbc:postgresql"),
    "mysql": ("mysql", "mariadb", "jdbc:mysql"),
    "sqlserver": ("sqlserver", "mssql", "jdbc:sqlserver", "Data Source=.*Initial Catalog"),
    "oracle": ("jdbc:oracle", "cx_oracle", "oracledb"),
    "sqlite": ("sqlite",),
    "mongodb": ("mongodb://", "pymongo", "mongoose"),
    "redis": ("redis://", "ioredis", "StackExchange.Redis"),
    "kafka": ("kafka", "confluent-kafka"),
    "rabbitmq": ("amqp://", "rabbitmq"),
}

EMBEDDED_SUBSTITUTES = {
    # datastore -> {language: embedded substitute} used only for the zero-dependency entry.
    "postgres": {"python": "sqlite", "node": "sqlite", "java": "h2", "dotnet": "sqlite"},
    "mysql": {"python": "sqlite", "node": "sqlite", "java": "h2", "dotnet": "sqlite"},
    "sqlserver": {"java": "h2", "dotnet": "sqlite"},
    "sqlite": {"python": "sqlite", "node": "sqlite", "java": "sqlite", "dotnet": "sqlite"},
}


def _evidence(root: Path, path: Path, marker: str) -> str:
    return f"{rel(root, path)}: {marker}"


def _detect_python(root: Path, out: dict[str, Any]) -> None:
    manifests = iter_files(root, ["requirements*.txt", "pyproject.toml", "setup.py", "Pipfile"])
    if not manifests:
        return
    blob = "\n".join(read_text(p).lower() for p in manifests)
    framework = None
    evidence: list[str] = []
    for name in PY_FRAMEWORKS:
        if re.search(rf"(^|[^a-z0-9_-]){re.escape(name)}([^a-z0-9_-]|$)", blob):
            framework = name
            for p in manifests:
                if name in read_text(p).lower():
                    evidence.append(_evidence(root, p, name))
            break
    entry = None
    for candidate in ("main.py", "app.py", "app/main.py", "src/main.py", "manage.py", "wsgi.py", "asgi.py"):
        if (root / candidate).is_file():
            entry = candidate
            evidence.append(_evidence(root, root / candidate, "entrypoint"))
            break
    profile = PY_FRAMEWORKS.get(framework or "", {})
    out["stacks"].append({
        "id": "python-service",
        "language": "python",
        "family": profile.get("family", "b29"),
        "framework": framework,
        "build_tool": "pip",
        "install_command": _pick_install_python(root),
        "start_command": _pick_start_python(root, framework, entry),
        "entrypoint": entry,
        "default_port": profile.get("port"),
        "readiness_path": profile.get("readiness"),
        "confidence": "high" if framework and entry else "low",
        "evidence": evidence or [_evidence(root, manifests[0], "python manifest")],
    })


def _pick_install_python(root: Path) -> str:
    if (root / "requirements.txt").is_file():
        return "python3 -m pip install --disable-pip-version-check -q -r requirements.txt"
    if (root / "pyproject.toml").is_file():
        return "python3 -m pip install --disable-pip-version-check -q -e ."
    return "python3 -m pip install --disable-pip-version-check -q ."


def _pick_start_python(root: Path, framework: str | None, entry: str | None) -> str | None:
    if framework == "django" and (root / "manage.py").is_file():
        return "python3 manage.py runserver 0.0.0.0:${SMOKE_PORT}"
    if framework in ("fastapi", "starlette"):
        module = (entry or "main.py").replace("/", ".")[:-3] if entry else "main"
        return f"python3 -m uvicorn {module}:app --host 0.0.0.0 --port ${{SMOKE_PORT}}"
    if entry:
        return f"python3 {entry}"
    return None


def _detect_node(root: Path, out: dict[str, Any]) -> None:
    pkg_path = root / "package.json"
    if not pkg_path.is_file():
        return
    try:
        pkg = json.loads(read_text(pkg_path))
    except json.JSONDecodeError:
        out["unknown"].append({"item": "package.json", "reason": "unparseable JSON"})
        return
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    scripts = pkg.get("scripts", {})
    framework = None
    meta: dict[str, Any] = {}
    evidence: list[str] = []
    for dep, info in NODE_FRAMEWORKS.items():
        if dep in deps:
            framework = info["name"]
            meta = info
            evidence.append(_evidence(root, pkg_path, f"dependencies.{dep}@{deps[dep]}"))
            break
    language = "typescript" if (root / "tsconfig.json").is_file() or any(
        d.startswith("typescript") for d in deps
    ) else "javascript"
    start = None
    for key in ("start:smoke", "start", "serve", "dev"):
        if key in scripts:
            start = f"npm run {key}"
            evidence.append(_evidence(root, pkg_path, f"scripts.{key}"))
            break
    if not start and pkg.get("main"):
        start = f"node {pkg['main']}"
    install = "npm ci --no-audit --no-fund" if (root / "package-lock.json").is_file() else "npm install --no-audit --no-fund"
    out["stacks"].append({
        "id": "node-app",
        "language": language,
        "family": meta.get("family", "b29"),
        "framework": framework,
        "build_tool": "npm",
        "install_command": install,
        "start_command": start,
        "entrypoint": pkg.get("main"),
        "default_port": meta.get("port"),
        "readiness_path": meta.get("readiness"),
        "confidence": "high" if framework and start else "low",
        "evidence": evidence or [_evidence(root, pkg_path, "package.json")],
    })


def _detect_flutter(root: Path, out: dict[str, Any]) -> None:
    pubspec = root / "pubspec.yaml"
    entrypoint = root / "lib" / "main.dart"
    web_entry = root / "web" / "index.html"
    if not pubspec.is_file() or not entrypoint.is_file():
        return
    text = read_text(pubspec)
    if not re.search(r"(?m)^\s*flutter:\s*$", text):
        return
    evidence = [
        _evidence(root, pubspec, "dependencies.flutter sdk"),
        _evidence(root, entrypoint, "Flutter entrypoint"),
    ]
    start = None
    if web_entry.is_file():
        evidence.append(_evidence(root, web_entry, "Flutter web bootstrap"))
        start = (
            "flutter run -d web-server --web-hostname 127.0.0.1 "
            "--web-port ${SMOKE_PORT} --no-pub"
        )
    out["stacks"].append({
        "id": "flutter-client",
        "language": "dart",
        "family": "b32",
        "framework": "flutter",
        "build_tool": "flutter",
        "install_command": "flutter pub get",
        "start_command": start,
        "entrypoint": "lib/main.dart",
        "default_port": 5173,
        "readiness_path": "/",
        "confidence": "high" if start else "medium",
        "evidence": evidence,
    })


def _detect_wechat_mini_program(root: Path, out: dict[str, Any]) -> None:
    project = root / "project.config.json"
    app = root / "app.json"
    runner = root / "scripts" / "frt-smoke-start.mjs"
    if not project.is_file() or not app.is_file():
        return
    try:
        config = json.loads(read_text(project))
    except json.JSONDecodeError:
        out["unknown"].append({"item": "project.config.json", "reason": "unparseable JSON"})
        return
    if config.get("compileType") != "miniprogram":
        return
    out["stacks"].append({
        "id": "wechat-mini-program-client",
        "language": "javascript",
        "family": "b32",
        "framework": "wechat-mini-program",
        "build_tool": "wechat-devtools",
        "install_command": None,
        "start_command": "node scripts/frt-smoke-start.mjs" if runner.is_file() else None,
        "entrypoint": "app.json",
        "default_port": 5173,
        "readiness_path": "/health",
        "confidence": "high" if runner.is_file() else "medium",
        "evidence": [
            _evidence(root, project, "compileType=miniprogram"),
            _evidence(root, app, "page manifest"),
            *([_evidence(root, runner, "bounded DevTools launch sidecar")] if runner.is_file() else []),
        ],
    })


def _detect_arkui(root: Path, out: dict[str, Any]) -> None:
    profile = root / "build-profile.json5"
    module = root / "entry" / "src" / "main" / "module.json5"
    runner = root / "scripts" / "frt-smoke-start.mjs"
    if not profile.is_file() or not module.is_file():
        return
    out["stacks"].append({
        "id": "arkui-client",
        "language": "ets",
        "family": "b32",
        "framework": "arkui",
        "build_tool": "hvigor",
        "install_command": None,
        "start_command": "node scripts/frt-smoke-start.mjs" if runner.is_file() else None,
        "entrypoint": "entry/src/main/module.json5",
        "default_port": 5173,
        "readiness_path": "/health",
        "confidence": "high" if runner.is_file() else "medium",
        "evidence": [
            _evidence(root, profile, "ArkUI build profile"),
            _evidence(root, module, "ArkUI entry module"),
            *([_evidence(root, runner, "bounded hvigor/hdc launch sidecar")] if runner.is_file() else []),
        ],
    })


def _detect_java(root: Path, out: dict[str, Any]) -> None:
    manifests = iter_files(root, ["pom.xml", "build.gradle", "build.gradle.kts"])
    if not manifests:
        return
    blob = "\n".join(read_text(p).lower() for p in manifests)
    framework = None
    evidence: list[str] = []
    for name in JAVA_FRAMEWORKS:
        if name in blob:
            framework = name
            for p in manifests:
                if name in read_text(p).lower():
                    evidence.append(_evidence(root, p, name))
            break
    gradle = any(p.name.startswith("build.gradle") for p in manifests)
    meta = JAVA_FRAMEWORKS.get(framework or "", {})
    out["stacks"].append({
        "id": "java-service",
        "language": "java",
        "family": meta.get("family", "b29"),
        "framework": framework,
        "build_tool": "gradle" if gradle else "maven",
        "install_command": "./gradlew --no-daemon build -x test" if gradle else "mvn -q -B -DskipTests package",
        "start_command": (
            "./gradlew --no-daemon bootRun" if gradle and framework == "spring-boot"
            else "java -jar $(ls target/*.jar | head -1)" if not gradle
            else None
        ),
        "entrypoint": None,
        "default_port": meta.get("port"),
        "readiness_path": meta.get("readiness"),
        "confidence": "medium" if framework else "low",
        "evidence": evidence or [_evidence(root, manifests[0], "java build file")],
    })


def _detect_dotnet(root: Path, out: dict[str, Any]) -> None:
    projects = iter_files(root, ["*.csproj", "*.fsproj"])
    if not projects:
        return
    evidence: list[str] = []
    framework = None
    for project in projects:
        text = read_text(project)
        for marker, info in DOTNET_FRAMEWORKS.items():
            if marker in text:
                framework = info["name"]
                evidence.append(_evidence(root, project, marker))
                break
    meta = next(iter(DOTNET_FRAMEWORKS.values())) if framework else {}
    primary = projects[0]
    out["stacks"].append({
        "id": "dotnet-service",
        "language": "csharp",
        "family": meta.get("family", "b29"),
        "framework": framework,
        "build_tool": "dotnet",
        "install_command": f"dotnet restore {rel(root, primary)}",
        "start_command": f"dotnet run --project {rel(root, primary)} --urls http://0.0.0.0:${{SMOKE_PORT}}",
        "entrypoint": rel(root, primary),
        "default_port": meta.get("port"),
        "readiness_path": meta.get("readiness"),
        "confidence": "medium" if framework else "low",
        "evidence": evidence or [_evidence(root, primary, "dotnet project")],
    })


def _detect_datastores(root: Path, out: dict[str, Any]) -> None:
    scan = iter_files(root, [
        "*.env", ".env*", "*.yml", "*.yaml", "*.json", "*.toml", "*.properties",
        "*.config", "*.xml", "*.ini",
    ])
    hits: dict[str, list[str]] = {}
    for path in scan:
        if path.name in ("package-lock.json",):
            continue
        text = read_text(path)
        low = text.lower()
        for engine, markers in DATASTORE_MARKERS.items():
            for marker in markers:
                if re.search(marker, low):
                    hits.setdefault(engine, []).append(_evidence(root, path, marker))
                    break
    schema_files = iter_files(root, ["*.sql", "schema.sql", "V*__*.sql"], max_depth=5)
    migration_dirs = sorted({
        rel(root, p.parent) for p in schema_files
        if any(part in ("migrations", "migration", "db", "sql", "flyway", "liquibase") for part in p.parts)
    })
    languages = [s["language"] for s in out["stacks"]]
    primary_lang = languages[0] if languages else None
    lang_key = {"typescript": "node", "javascript": "node"}.get(primary_lang or "", primary_lang or "")
    for engine, evidence in sorted(hits.items()):
        substitute = EMBEDDED_SUBSTITUTES.get(engine, {}).get(lang_key)
        out["datastores"].append({
            "engine": engine,
            "role": "primary" if engine in ("postgres", "mysql", "sqlserver", "oracle", "sqlite", "mongodb") else "supporting",
            "schema_files": [rel(root, p) for p in schema_files] if engine not in ("redis", "kafka", "rabbitmq") else [],
            "migration_dirs": migration_dirs if engine not in ("redis", "kafka", "rabbitmq") else [],
            "embedded_substitute": substitute,
            "embedded_substitute_status": "available" if substitute else "unavailable",
            "evidence": evidence[:5],
        })
    if schema_files and not out["datastores"]:
        out["datastores"].append({
            "engine": "sql-unspecified",
            "role": "primary",
            "schema_files": [rel(root, p) for p in schema_files],
            "migration_dirs": migration_dirs,
            "embedded_substitute": None,
            "embedded_substitute_status": "unavailable",
            "evidence": [_evidence(root, schema_files[0], "sql schema file")],
        })
        out["unknown"].append({
            "item": "datastore engine",
            "reason": "SQL schema found but no engine marker; declare it in smoke/profile.json before certification",
        })


def _detect_env_contract(root: Path, out: dict[str, Any]) -> None:
    for name in (".env.example", ".env.sample", ".env.template", "env.example"):
        path = root / name
        if path.is_file():
            out["env_contract_files"].append(rel(root, path))
    for candidate in ("application.yml", "application.yaml", "application.properties",
                      "appsettings.json", "appsettings.Development.json", "config/default.json"):
        for path in iter_files(root, [candidate]):
            out["env_contract_files"].append(rel(root, path))
    out["env_contract_files"] = sorted(set(out["env_contract_files"]))


def _detect_api_contract(root: Path, out: dict[str, Any]) -> None:
    for path in iter_files(root, ["openapi.json", "openapi.yaml", "openapi.yml", "swagger.json", "*.proto"]):
        out["api_contract_files"].append(rel(root, path))
    out["api_contract_files"] = sorted(set(out["api_contract_files"]))


def detect(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    out: dict[str, Any] = {
        "schema": f"{SCHEMA_PREFIX}.project-profile/1",
        "generated_at": utc_now(),
        # Pack content must remain portable after clone, archive extraction or
        # atomic publish from a staging directory.  Never digest or disclose an
        # operator's absolute workstation path.
        "project_root": ".",
        "stacks": [],
        "datastores": [],
        "env_contract_files": [],
        "api_contract_files": [],
        "unsupported": [],
        "unknown": [],
    }
    _detect_python(root, out)
    _detect_node(root, out)
    _detect_flutter(root, out)
    _detect_wechat_mini_program(root, out)
    _detect_arkui(root, out)
    _detect_java(root, out)
    _detect_dotnet(root, out)
    _detect_datastores(root, out)
    _detect_env_contract(root, out)
    _detect_api_contract(root, out)

    if not out["stacks"]:
        out["unknown"].append({
            "item": "runnable stack",
            "reason": "no supported service or client manifest found under the scanned depth",
        })
    for stack in out["stacks"]:
        if not stack.get("start_command"):
            out["unknown"].append({
                "item": f"start command for {stack['id']}",
                "reason": "no start script detected; declare it before the pack can be certified",
            })
        if not stack.get("default_port") and stack.get("family") != "b31":
            out["unknown"].append({
                "item": f"listen port for {stack['id']}",
                "reason": "no framework default known; declare it before the pack can be certified",
            })
    if len(out["stacks"]) > 1:
        out["polyglot"] = True
        out["stacks"][0]["role"] = "primary"
        for stack in out["stacks"][1:]:
            stack["role"] = "secondary"
    else:
        out["polyglot"] = False
        for stack in out["stacks"]:
            stack["role"] = "primary"
    out["profile_digest"] = "pending"
    digest_input = {k: v for k, v in out.items() if k not in ("generated_at", "profile_digest")}
    out["profile_digest"] = canonical_digest(digest_input)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect the runnable profile of a project")
    parser.add_argument("project_root")
    parser.add_argument("--write", action="store_true", help="write smoke/profile.json")
    args = parser.parse_args()
    root = Path(args.project_root)
    if not root.is_dir():
        print(f"error: not a directory: {root}")
        return 2
    profile = detect(root)
    if args.write:
        path = write_json(smoke_dir(root) / "profile.json", profile)
        print(f"wrote {path} ({file_digest(path)})")
    else:
        print(json.dumps(profile, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
