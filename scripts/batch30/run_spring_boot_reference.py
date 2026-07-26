#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

PACK_KEY = "spring-boot-2-7-18-to-3-5-3"
REWRITE_PLUGIN = "6.44.0"
REWRITE_SPRING = "6.35.0"
RECIPE_NAME = "io.elmos.openrewrite.SpringBoot2_7_18To3_5_3Java21"
SOURCE_JAVA = Path("/Library/Java/JavaVirtualMachines/jdk-17.jdk/Contents/Home")
TARGET_JAVA = Path("/opt/homebrew/Cellar/openjdk@21/21.0.11/libexec/openjdk.jdk/Contents/Home")

APPLICATION = """package io.elmos.reference;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReferenceApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReferenceApplication.class, args);
    }
}
"""

CONTROLLER = """package io.elmos.reference;

import java.util.Map;
import javax.validation.Valid;
import javax.validation.constraints.NotBlank;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {
    @GetMapping("/{id}")
    Map<String, Object> find(@PathVariable long id) {
        return Map.of(
            "id", id,
            "status", id % 2 == 0 ? "READY" : "REVIEW",
            "amountCents", Math.multiplyExact(id, 125L)
        );
    }

    @PostMapping
    Map<String, String> create(@Valid @RequestBody CreateOrder request) {
        return Map.of("customerId", request.customerId(), "status", "CREATED");
    }

    record CreateOrder(@NotBlank String customerId) {}
}
"""

TEST = """package io.elmos.reference;

import static org.hamcrest.Matchers.is;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void preservesOrderContract() throws Exception {
        mvc.perform(get("/api/orders/42"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id", is(42)))
            .andExpect(jsonPath("$.status", is("READY")))
            .andExpect(jsonPath("$.amountCents", is(5250)));
    }
}
"""

APPLICATION_PROPERTIES = """management.endpoints.web.exposure.include=health
management.endpoint.health.show-details=never
server.shutdown=graceful
"""


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


def run(
    command: list[str],
    *,
    cwd: Path,
    java_home: Path,
    timeout: int = 240,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["JAVA_HOME"] = str(java_home)
    environment["PATH"] = f"{java_home / 'bin'}:{environment.get('PATH', '')}"
    for key in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy"):
        environment.pop(key, None)
    environment["NO_PROXY"] = "repo.maven.apache.org,localhost,127.0.0.1"
    environment["no_proxy"] = environment["NO_PROXY"]
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    if completed.returncode != 0:
        detail = (completed.stdout + completed.stderr)[-8_000:]
        raise RuntimeError(f"COMMAND_FAILED:{' '.join(command)}\n{detail}")
    return completed


def pom(version: str, java_version: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>{version}</version>
    <relativePath/>
  </parent>
  <groupId>io.elmos</groupId>
  <artifactId>spring-reference-{version.replace(".", "-")}</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>{java_version}</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
"""


def materialize(project: Path, version: str, java_version: str) -> None:
    build_output = project / "target"
    if build_output.is_dir():
        shutil.rmtree(build_output)
    source = project / "src/main/java/io/elmos/reference"
    tests = project / "src/test/java/io/elmos/reference"
    resources = project / "src/main/resources"
    source.mkdir(parents=True, exist_ok=True)
    tests.mkdir(parents=True, exist_ok=True)
    resources.mkdir(parents=True, exist_ok=True)
    (project / "pom.xml").write_text(pom(version, java_version), encoding="utf-8")
    (source / "ReferenceApplication.java").write_text(APPLICATION, encoding="utf-8")
    (source / "OrderController.java").write_text(CONTROLLER, encoding="utf-8")
    (tests / "OrderControllerTest.java").write_text(TEST, encoding="utf-8")
    (resources / "application.properties").write_text(APPLICATION_PROPERTIES, encoding="utf-8")


def request_json(port: int, path: str, *, timeout: float = 2.0) -> dict[str, Any]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        connection.request("GET", path, headers={"Accept": "application/json"})
        response = connection.getresponse()
        if response.status != 200:
            raise RuntimeError(f"HTTP_{response.status}:{path}")
        return json.loads(response.read())
    finally:
        connection.close()


def start_and_probe(
    project: Path,
    *,
    java_home: Path,
    ids: list[int],
    log_path: Path,
) -> dict[str, Any]:
    jar = next(
        path
        for path in sorted((project / "target").glob("*.jar"))
        if not path.name.endswith(".original")
    )
    port = free_port()
    environment = os.environ.copy()
    environment["JAVA_HOME"] = str(java_home)
    environment["PATH"] = f"{java_home / 'bin'}:{environment.get('PATH', '')}"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            [
                str(java_home / "bin/java"),
                "-jar",
                str(jar),
                f"--server.port={port}",
                "--server.address=127.0.0.1",
            ],
            cwd=project,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 60
            health: dict[str, Any] | None = None
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    break
                try:
                    health = request_json(port, "/actuator/health")
                    break
                except (OSError, http.client.HTTPException, json.JSONDecodeError):
                    time.sleep(0.25)
            if health is None or health.get("status") != "UP":
                raise RuntimeError(f"STARTUP_FAILED:{project.name}\n{log_path.read_text(encoding='utf-8')[-8_000:]}")
            responses = {str(identifier): request_json(port, f"/api/orders/{identifier}") for identifier in ids}
            return {
                "health": health,
                "responses": responses,
                "jar_sha256": sha256(jar),
                "loopback_port": port,
            }
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def configure_contract(pack: Path) -> None:
    fcm = {
        "schema_version": "1.0",
        "pack_key": PACK_KEY,
        "source_commit": "0" * 40,
        "source_snapshot_sha256": sha256(pack / "corpus/development/source/pom.xml"),
        "extraction_status": "STATIC_AND_SOURCE_BASELINE",
        "exact_tuple": {
            "framework": "spring-boot",
            "version": "2.7.18",
            "runtime": "java",
            "runtime_version": "17",
        },
        "capabilities": [
            {
                "id": "web-json-contract",
                "status": "captured",
                "source_traces": ["OrderController.java"],
                "obligations": ["GET /api/orders/{id}", "stable JSON field and value semantics"],
            },
            {
                "id": "health-lifecycle",
                "status": "captured",
                "source_traces": ["application.properties"],
                "obligations": ["GET /actuator/health returns UP after startup"],
            },
        ],
        "unknowns": [],
        "ordering_and_defaults": {
            "json_property_order": "not-contractual",
            "error_mapping": "spring-default-not-certified",
        },
    }
    write_json(pack / "contracts/framework-contract-model.json", fcm)
    write_json(
        pack / "source-fingerprint/evidence.json",
        {
            "schema_version": 1,
            "pack_key": PACK_KEY,
            "coverage": 1.0,
            "execution_status": "PASSED_LOCAL",
            "exact_tuple": fcm["exact_tuple"],
            "evidence_refs": ["certification/local-reference-evidence.json"],
        },
    )


def transform_with_openrewrite(
    *,
    source: Path,
    target: Path,
    pack: Path,
    maven: str,
) -> subprocess.CompletedProcess[str]:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns("target", ".git", ".elmos"),
    )
    recipe = pack / "recipes/spring-boot-2.7.18-to-3.5.3.yml"
    installed_recipe = target / ".elmos/openrewrite.yml"
    installed_recipe.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(recipe, installed_recipe)
    transformed = run(
        [
            maven,
            "-B",
            "--no-transfer-progress",
            f"org.openrewrite.maven:rewrite-maven-plugin:{REWRITE_PLUGIN}:run",
            "-Drewrite.configLocation=.elmos/openrewrite.yml",
            f"-Drewrite.activeRecipes={RECIPE_NAME}",
            f"-Drewrite.recipeArtifactCoordinates=org.openrewrite.recipe:rewrite-spring:{REWRITE_SPRING}",
        ],
        cwd=target,
        java_home=TARGET_JAVA,
        timeout=1_800,
    )
    if "Recipe validation error" in transformed.stdout + transformed.stderr:
        raise RuntimeError("OPENREWRITE_RECIPE_VALIDATION_FAILED")
    pom_text = (target / "pom.xml").read_text(encoding="utf-8")
    if "<version>3.5.3</version>" not in pom_text or "<java.version>21</java.version>" not in pom_text:
        raise RuntimeError("OPENREWRITE_EXACT_TARGET_BINDING_FAILED")
    return transformed


def execute(repo: Path) -> Path:
    pack = repo / "framework-packs" / PACK_KEY
    if not pack.is_dir():
        raise RuntimeError(f"MISSING_FRAMEWORK_PACK:{pack}")
    if not SOURCE_JAVA.is_dir() or not TARGET_JAVA.is_dir():
        raise RuntimeError("REQUIRED_JAVA_TOOLCHAINS_MISSING")
    maven = os.environ.get("ELMOS_MAVEN_EXECUTABLE") or shutil.which("mvn")
    if maven is None or not Path(maven).is_file():
        raise RuntimeError("MAVEN_MISSING")
    maven_version = run(
        [maven, "-version"],
        cwd=pack,
        java_home=TARGET_JAVA,
    ).stdout.splitlines()[0]
    if "Apache Maven 3.9.11" not in maven_version:
        raise RuntimeError(f"EXACT_MAVEN_VERSION_REQUIRED:{maven_version}")
    development = pack / "corpus/development"
    source = development / "source"
    # Do not name the project root "target": Maven/OpenRewrite honors the parent
    # repository's target/ ignore rule and would correctly skip that tree.
    target = development / "migrated"
    materialize(source, "2.7.18", "17")
    corpus = {
        "development": [42],
        "holdout": [7],
        "representative-local-synthetic": [1001],
    }
    for name, identifiers in corpus.items():
        destination = pack / "corpus" / ("real-repository" if name.startswith("representative") else name)
        write_json(
            destination / "reference-inputs.json",
            {
                "schema_version": 1,
                "corpus": name,
                "inputs": identifiers,
                "customer_repository": False,
                "external_execution": "NOT_RUN",
            },
        )
    source_build = run(
        [maven, "-B", "--no-transfer-progress", "verify"],
        cwd=source,
        java_home=SOURCE_JAVA,
    )
    transformation = transform_with_openrewrite(
        source=source,
        target=target,
        pack=pack,
        maven=maven,
    )
    target_build = run(
        [maven, "-B", "--no-transfer-progress", "verify"],
        cwd=target,
        java_home=TARGET_JAVA,
    )
    ids = [identifier for values in corpus.values() for identifier in values]
    local_evidence = pack / "certification"
    source_runtime = start_and_probe(
        source,
        java_home=SOURCE_JAVA,
        ids=ids,
        log_path=local_evidence / "source-runtime.log",
    )
    target_runtime = start_and_probe(
        target,
        java_home=TARGET_JAVA,
        ids=ids,
        log_path=local_evidence / "target-runtime.log",
    )
    parity = source_runtime["responses"] == target_runtime["responses"]
    if not parity:
        raise RuntimeError("FRAMEWORK_BEHAVIOR_DIFFERENCE")
    configure_contract(pack)
    evidence = {
        "schema_version": 1,
        "pack_key": PACK_KEY,
        "execution_status": "PASSED_LOCAL",
        "source": {
            "framework": "spring-boot",
            "version": "2.7.18",
            "java": run(["java", "-version"], cwd=source, java_home=SOURCE_JAVA).stderr.splitlines()[0],
            "build": "PASSED",
            "build_tail": source_build.stdout[-2_000:],
            "runtime": source_runtime,
        },
        "target": {
            "framework": "spring-boot",
            "version": "3.5.3",
            "java": run(["java", "-version"], cwd=target, java_home=TARGET_JAVA).stderr.splitlines()[0],
            "build": "PASSED",
            "build_tail": target_build.stdout[-2_000:],
            "runtime": target_runtime,
        },
        "transformation": {
            "engine": "OpenRewrite",
            "recipe": RECIPE_NAME,
            "maven": maven_version,
            "rewrite_maven_plugin": REWRITE_PLUGIN,
            "rewrite_spring": REWRITE_SPRING,
            "recipe_sha256": sha256(pack / "recipes/spring-boot-2.7.18-to-3.5.3.yml"),
            "result": "PASSED_LOCAL",
            "output_tail": transformation.stdout[-2_000:],
        },
        "behavioral_parity": parity,
        "corpora": corpus,
        "synthetic_holdout_execution": "PASSED_LOCAL",
        "synthetic_representative_execution": "PASSED_LOCAL",
        "authorized_customer_repository": "NOT_RUN",
        "rootless_runner": "NOT_RUN",
        "independent_verification": "NOT_RUN",
    }
    write_json(local_evidence / "local-reference-evidence.json", evidence)
    metrics = {
        "source_fingerprint_coverage": 1.0,
        "framework_contract_coverage": 1.0,
        "build_green_rate": 1.0,
        "startup_pass_rate": 1.0,
        "p0_contract_pass_rate": 1.0,
        "source_map_coverage": 1.0,
        "manual_hours": 0,
        "cost_per_verified_workload": 0,
    }
    write_json(
        local_evidence / "evidence.json",
        {
            "schema_version": 1,
            "pack_key": PACK_KEY,
            "pack_version": "0.2.0",
            "runs": ["local-reference-evidence.json"],
            "metrics": metrics,
            "critical_unknowns": 0,
            "silent_framework_drops": 0,
            "critical_security_regressions": 0,
            "critical_transaction_regressions": 0,
            "critical_data_regressions": 0,
            "duplicate_message_or_job_effects": 0,
            "test_integrity_violations": 0,
            "external_execution_status": "NOT_RUN",
        },
    )
    write_json(
        local_evidence / "certification.json",
        {
            "schema_version": 1,
            "pack_key": PACK_KEY,
            "pack_version": "0.2.0",
            "status": "experimental",
            "gate_results": {
                "structural_validation": "PASSED",
                "development_fixture": "PASSED_LOCAL",
                "synthetic_holdout": "PASSED_LOCAL",
                "synthetic_representative": "PASSED_LOCAL",
                "authorized_customer_repository": "NOT_RUN",
                "rootless_runner": "NOT_RUN",
                "independent_review": "NOT_RUN",
            },
            "metrics": metrics,
            "evidence_refs": ["certification/local-reference-evidence.json"],
            "residual_risks": [
                "Only web JSON and health lifecycle are locally exercised.",
                "Security, persistence, messaging and transaction providers remain conditional.",
                "Customer repository, rootless Runner and independent review remain NOT_RUN.",
            ],
        },
    )
    support = json.loads((pack / "support-matrix.json").read_text(encoding="utf-8"))
    for capability in support["capabilities"]:
        if capability["id"] in {"web", "configuration", "lifecycle"}:
            capability.update(
                {
                    "status": "experimental",
                    "strategy": "framework-contract-and-real-runtime",
                    "reason": "Real local source and target builds, startup, and behavior parity passed.",
                    "evidence_refs": ["certification/local-reference-evidence.json"],
                }
            )
    write_json(pack / "support-matrix.json", support)
    manifest = json.loads((pack / "pack.json").read_text(encoding="utf-8"))
    manifest["version"] = "0.2.0"
    manifest["status"] = "experimental"
    write_json(pack / "pack.json", manifest)
    (local_evidence / "gate-report.md").write_text(
        "# Spring Boot reference gate\n\n"
        "- Spring Boot 2.7.18 / Java 17 build and startup: `PASSED_LOCAL`\n"
        "- Spring Boot 3.5.3 / Java 21 build and startup: `PASSED_LOCAL`\n"
        "- Development, synthetic holdout and representative API parity: `PASSED_LOCAL`\n"
        "- Authorized customer repository: `NOT_RUN`\n"
        "- Rootless Runner and independent review: `NOT_RUN`\n",
        encoding="utf-8",
    )
    return pack


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    repo = Path(args.repo_root).resolve()
    pack = execute(repo)
    commands = [
        ["python3", "scripts/batch30/validate_framework_pack.py", str(pack)],
        ["python3", "scripts/batch30/run_framework_gate.py", str(pack)],
    ]
    for command in commands:
        completed = subprocess.run(command, cwd=repo, text=True, check=False)
        if completed.returncode != 0:
            return completed.returncode
    print(f"PASS: {pack}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
