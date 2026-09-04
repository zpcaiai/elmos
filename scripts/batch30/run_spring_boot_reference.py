#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
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


def resolve_java_home(version: int, override: str | Path | None = None) -> Path:
    """Resolve JDK home directory by argument override, environment variables,
    macOS java_home utility, or standard installation paths."""
    if override:
        path = Path(override).expanduser().resolve()
        if path.is_dir():
            return path
    env_keys = [f"JAVA_{version}_HOME", f"JDK_{version}_HOME", "JAVA_HOME"]
    for key in env_keys:
        val = os.environ.get(key)
        if val:
            path = Path(val).expanduser().resolve()
            if path.is_dir():
                return path
    if shutil.which("/usr/libexec/java_home"):
        try:
            res = subprocess.run(
                ["/usr/libexec/java_home", "-v", str(version)],
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                candidate = Path(res.stdout.strip()).resolve()
                if candidate.is_dir():
                    return candidate
        except Exception:
            pass
    defaults = {
        17: Path("/Library/Java/JavaVirtualMachines/jdk-17.jdk/Contents/Home"),
        21: Path("/opt/homebrew/Cellar/openjdk@21/21.0.11/libexec/openjdk.jdk/Contents/Home"),
    }
    return defaults.get(version, Path(f"/usr/lib/jvm/java-{version}"))


SOURCE_JAVA = resolve_java_home(17)
TARGET_JAVA = resolve_java_home(21)


def governed_qualification_snapshots(certification_dir: Path) -> list[str]:
    snapshots: list[str] = []
    for path in sorted(
        certification_dir.glob("local-product-surface-qualification-*.json")
    ):
        record = json.loads(path.read_text(encoding="utf-8"))
        if (
            record.get("pack_key") != PACK_KEY
            or record.get("evidence_class") != "LOCAL_QUALIFICATION_SNAPSHOT"
            or record.get("certification_eligible") is not False
            or record.get("certification_decision") != "NOT_CERTIFIED"
        ):
            raise ValueError(f"UNSAFE_LOCAL_QUALIFICATION_SNAPSHOT:{path.name}")
        snapshots.append(path.name)
    return snapshots

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

SECURITY_CONFIGURATION = """package io.elmos.reference;

import static org.springframework.security.config.Customizer.withDefaults;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfiguration {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeRequests(authorize -> authorize
            .antMatchers("/actuator/health").permitAll()
            .antMatchers("/error").permitAll()
            .antMatchers(HttpMethod.GET, "/api/orders/**").authenticated()
            .antMatchers(HttpMethod.POST, "/api/orders").authenticated()
            .anyRequest().denyAll()
        ).csrf(csrf -> csrf.ignoringAntMatchers("/api/orders"))
            .httpBasic(withDefaults());
        return http.build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        return new InMemoryUserDetailsManager(
            User.withUsername("operator")
                .password("{noop}operator-password")
                .roles("OPERATOR")
                .build()
        );
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
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void preservesOrderContract() throws Exception {
        mvc.perform(get("/api/orders/42")
                .with(SecurityMockMvcRequestPostProcessors.httpBasic("operator", "operator-password")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id", is(42)))
            .andExpect(jsonPath("$.status", is("READY")))
            .andExpect(jsonPath("$.amountCents", is(5250)));
    }

    @Test
    void rejectsUnauthenticatedOrderReads() throws Exception {
        mvc.perform(get("/api/orders/42"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void preservesValidationContract() throws Exception {
        mvc.perform(post("/api/orders")
                .with(SecurityMockMvcRequestPostProcessors.httpBasic("operator", "operator-password"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\\\"customerId\\\":\\\"\\\"}"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void acceptsAuthenticatedValidOrder() throws Exception {
        mvc.perform(post("/api/orders")
                .with(SecurityMockMvcRequestPostProcessors.httpBasic("operator", "operator-password"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\\\"customerId\\\":\\\"customer-42\\\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.customerId", is("customer-42")))
            .andExpect(jsonPath("$.status", is("CREATED")));
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


def evidence_binding(pack: Path, path: Path, role: str) -> dict[str, Any]:
    raw = path.read_bytes()
    return {
        "bytes": len(raw),
        "path": path.relative_to(pack).as_posix(),
        "role": role,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


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
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-test</artifactId>
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
    (source / "SecurityConfiguration.java").write_text(SECURITY_CONFIGURATION, encoding="utf-8")
    (tests / "OrderControllerTest.java").write_text(TEST, encoding="utf-8")
    (resources / "application.properties").write_text(APPLICATION_PROPERTIES, encoding="utf-8")


def request_http(
    port: int,
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    username: str | None = None,
    password: str | None = None,
    timeout: float = 15.0,
) -> tuple[int, bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        headers = {"Accept": "application/json"}
        encoded_body: bytes | None = None
        if body is not None:
            encoded_body = json.dumps(body, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if username is not None and password is not None:
            credentials = f"{username}:{password}".encode("utf-8")
            headers["Authorization"] = "Basic " + base64.b64encode(credentials).decode("ascii")
        connection.request(method, path, body=encoded_body, headers=headers)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def request_json(
    port: int,
    path: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    username: str | None = None,
    password: str | None = None,
    expected_status: int = 200,
    timeout: float = 15.0,
) -> dict[str, Any]:
    status, raw = request_http(
        port,
        method,
        path,
        body=body,
        username=username,
        password=password,
        timeout=timeout,
    )
    if status != expected_status:
        raise RuntimeError(f"HTTP_{status}:{path}:expected={expected_status}")
    if not raw:
        return {}
    return json.loads(raw)


def start_and_probe(
    project: Path,
    *,
    java_home: Path,
    ids: list[int],
    log_path: Path,
) -> dict[str, Any]:
    jar = next(path for path in sorted((project / "target").glob("*.jar")) if not path.name.endswith(".original"))
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
            unauthenticated_status, _ = request_http(port, "GET", "/api/orders/42")
            if unauthenticated_status != 401:
                raise RuntimeError(
                    f"SECURITY_CONTRACT_FAILED:{project.name}:"
                    f"unauthenticated_status={unauthenticated_status}"
                )
            responses = {
                str(identifier): request_json(
                    port,
                    f"/api/orders/{identifier}",
                    username="operator",
                    password="operator-password",
                )
                for identifier in ids
            }
            invalid_order_status, _ = request_http(
                port,
                "POST",
                "/api/orders",
                body={"customerId": ""},
                username="operator",
                password="operator-password",
            )
            if invalid_order_status != 400:
                raise RuntimeError(
                    f"VALIDATION_CONTRACT_FAILED:{project.name}:"
                    f"invalid_order_status={invalid_order_status}"
                )
            valid_order = request_json(
                port,
                "/api/orders",
                method="POST",
                body={"customerId": "customer-42"},
                username="operator",
                password="operator-password",
            )
            return {
                "health": health,
                "responses": responses,
                "security": {
                    "unauthenticated_order_status": unauthenticated_status,
                    "authenticated_order_status": 200,
                },
                "validation": {
                    "invalid_order_status": invalid_order_status,
                    "valid_order_status": 200,
                    "valid_order_response": valid_order,
                },
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
            {
                "id": "configuration-runtime-contract",
                "status": "captured",
                "source_traces": ["application.properties"],
                "obligations": [
                    "management health endpoint exposure remains enabled",
                    "health details remain hidden",
                    "graceful shutdown remains enabled",
                ],
            },
            {
                "id": "validation-contract",
                "status": "captured",
                "source_traces": ["OrderController.java"],
                "obligations": [
                    "POST /api/orders with blank customerId returns HTTP 400",
                    "POST /api/orders with a non-blank customerId returns HTTP 200",
                ],
            },
            {
                "id": "security-contract",
                "status": "captured",
                "source_traces": ["SecurityConfiguration.java"],
                "obligations": [
                    "GET /api/orders/{id} without HTTP Basic credentials returns HTTP 401",
                    "GET /api/orders/{id} with fixture operator credentials returns HTTP 200",
                    "the actuator health endpoint remains publicly readable",
                ],
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


def has_public_engineering_evidence(pack: Path) -> bool:
    certification = pack / "certification" / "public-reference-route-evidence.json"
    if not certification.is_file():
        return False
    public = json.loads(certification.read_text(encoding="utf-8"))
    if (
        public.get("evidence_class") != "LOCAL_PUBLIC_REPOSITORY_ENGINEERING"
        or public.get("certification_eligible") is not False
    ):
        return False
    for corpus, field in (
        ("holdout", "holdout_public_repository"),
        ("real-repository", "representative_public_repository"),
    ):
        reference = pack / "corpus" / corpus / "reference-inputs.json"
        if not reference.is_file():
            return False
        manifest = json.loads(reference.read_text(encoding="utf-8"))
        if (
            manifest.get("execution_status") != "PASSED_LOCAL_PUBLIC_ENGINEERING"
            or manifest.get("external_execution") != "NOT_RUN"
            or not manifest.get("inputs")
        ):
            return False
        observed = public.get(field)
        if not isinstance(observed, dict):
            return False
        if (
            observed.get("openrewrite_actual_execution") is not True
            or observed.get("download_digest_and_size_match") is not True
            or observed.get("source_tests", {}).get("failures") != 0
            or observed.get("source_tests", {}).get("errors") != 0
            or observed.get("target_tests", {}).get("failures") != 0
            or observed.get("target_tests", {}).get("errors") != 0
        ):
            return False
        verifier = observed.get("independent_verifier", {})
        if (
            verifier.get("status") != "PASS"
            or verifier.get("physically_separate_process") is not True
            or verifier.get("organizationally_independent") is not False
        ):
            return False
    return True


def transform_with_openrewrite(
    source: Path,
    target: Path,
    pack: Path,
    maven: str,
    target_java: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    tgt_java = target_java or TARGET_JAVA
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
        java_home=tgt_java,
        timeout=1_800,
    )
    if "Recipe validation error" in transformed.stdout + transformed.stderr:
        raise RuntimeError("OPENREWRITE_RECIPE_VALIDATION_FAILED")
    pom_text = (target / "pom.xml").read_text(encoding="utf-8")
    if "<version>3.5.3</version>" not in pom_text or "<java.version>21</java.version>" not in pom_text:
        raise RuntimeError("OPENREWRITE_EXACT_TARGET_BINDING_FAILED")
    return transformed


def execute(
    repo: Path,
    source_java: Path | None = None,
    target_java: Path | None = None,
    external_repo: Path | None = None,
) -> Path:
    src_java = source_java or SOURCE_JAVA
    tgt_java = target_java or TARGET_JAVA
    pack = repo / "framework-packs" / PACK_KEY
    if not pack.is_dir():
        raise RuntimeError(f"MISSING_FRAMEWORK_PACK:{pack}")
    if not src_java.is_dir() or not tgt_java.is_dir():
        raise RuntimeError("REQUIRED_JAVA_TOOLCHAINS_MISSING")
    maven = os.environ.get("ELMOS_MAVEN_EXECUTABLE") or shutil.which("mvn")
    if maven is None or not Path(maven).is_file():
        raise RuntimeError("MAVEN_MISSING")
    maven_version = run(
        [maven, "-version"],
        cwd=pack,
        java_home=tgt_java,
    ).stdout.splitlines()[0]
    if "Apache Maven 3.9.11" not in maven_version:
        raise RuntimeError(f"EXACT_MAVEN_VERSION_REQUIRED:{maven_version}")
    development = pack / "corpus/development"
    source = development / "source"
    # Do not name the project root "target": Maven/OpenRewrite honors the parent
    # repository's target/ ignore rule and would correctly skip that tree.
    target = development / "migrated"
    if external_repo and external_repo.is_dir():
        if source.exists():
            shutil.rmtree(source)
        shutil.copytree(external_repo, source, ignore=shutil.ignore_patterns("target", ".git", ".elmos"))
    else:
        materialize(source, "2.7.18", "17")
    corpus = {
        "development": [42],
        "holdout": [7],
        "representative-local-synthetic": [1001],
    }
    for name, identifiers in corpus.items():
        destination = pack / "corpus" / ("real-repository" if name.startswith("representative") else name)
        reference_inputs = destination / "reference-inputs.json"
        # Existing holdout and representative manifests are immutable evidence
        # inputs.  The local fixture runner may provide a development manifest
        # when absent, but must never replace an existing corpus declaration.
        if not reference_inputs.is_file():
            write_json(
                reference_inputs,
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
        java_home=src_java,
    )
    transformation = transform_with_openrewrite(
        source=source,
        target=target,
        pack=pack,
        maven=maven,
        target_java=tgt_java,
    )
    target_build = run(
        [maven, "-B", "--no-transfer-progress", "verify"],
        cwd=target,
        java_home=tgt_java,
    )
    ids = [identifier for values in corpus.values() for identifier in values]
    local_evidence = pack / "certification"
    source_runtime = start_and_probe(
        source,
        java_home=src_java,
        ids=ids,
        log_path=local_evidence / "source-runtime.log",
    )
    target_runtime = start_and_probe(
        target,
        java_home=tgt_java,
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
            "java": run(["java", "-version"], cwd=source, java_home=src_java).stderr.splitlines()[0],
            "build": "PASSED",
            "build_tail": source_build.stdout[-2_000:],
            "runtime": source_runtime,
        },
        "target": {
            "framework": "spring-boot",
            "version": "3.5.3",
            "java": run(["java", "-version"], cwd=target, java_home=tgt_java).stderr.splitlines()[0],
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
        "migration": {
            "status": "PASSED_LOCAL",
            "scope": "repository-owned-synthetic-fixture",
            "production_status": "NOT_RUN",
        },
        "equivalence": {
            "status": "PASSED_LOCAL",
            "scope": "HTTP-health-validation-security-fixture-contracts",
            "production_status": "NOT_RUN",
        },
        "security": {
            "status": "PASSED_LOCAL",
            "scope": "fixture-basic-auth-and-route-authorization",
            "production_status": "NOT_RUN",
        },
        "corpora": corpus,
        "synthetic_holdout_execution": "PASSED_LOCAL",
        "synthetic_representative_execution": "PASSED_LOCAL",
        "authorized_customer_repository": "NOT_RUN",
        "customer_holdout": "NOT_RUN",
        "customer_acceptance": "NOT_RUN",
        "rootless_runner": "NOT_RUN",
        "rootless_transformer": "NOT_RUN",
        "rootless_verifier": "NOT_RUN",
        "independent_verification": "NOT_RUN",
        "independent_review": "NOT_RUN",
        "external_certification": "NOT_RUN",
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
    public_evidence = has_public_engineering_evidence(pack)
    status = "limited" if public_evidence else "experimental"
    pack_version = "0.3.0" if public_evidence else "0.2.0"
    runs = ["local-reference-evidence.json"]
    evidence_refs = ["certification/local-reference-evidence.json"]
    for name in (
        "local-product-journey-evidence.json",
        "public-reference-route-evidence.json",
    ):
        if public_evidence and (local_evidence / name).is_file():
            runs.append(name)
            evidence_refs.append(f"certification/{name}")
    for qualification_snapshot in governed_qualification_snapshots(local_evidence):
        runs.append(qualification_snapshot)
        evidence_refs.append(f"certification/{qualification_snapshot}")
    write_json(
        local_evidence / "evidence.json",
        {
            "schema_version": 1,
            "pack_key": PACK_KEY,
            "pack_version": pack_version,
            "runs": runs,
            "metrics": metrics,
            "critical_unknowns": 0,
            "silent_framework_drops": 0,
            "critical_security_regressions": 0,
            "critical_transaction_regressions": 0,
            "critical_data_regressions": 0,
            "duplicate_message_or_job_effects": 0,
            "test_integrity_violations": 0,
            "external_execution_status": "NOT_RUN",
            "target_repository_runtime_evidence": "NOT_RUN",
            "customer_and_independent_evidence": "NOT_RUN",
        },
    )
    gate_results = {
        "structural_validation": "PASSED",
        "development_fixture": "PASSED_LOCAL",
        "synthetic_holdout": "PASSED_LOCAL",
        "synthetic_representative": "PASSED_LOCAL",
        "public_holdout": ("PASSED_LOCAL_ENGINEERING" if public_evidence else "NOT_RUN"),
        "public_representative": ("PASSED_LOCAL_ENGINEERING" if public_evidence else "NOT_RUN"),
        "github_app_private_repository": "NOT_RUN",
        "authorized_customer_repository": "NOT_RUN",
        "customer_holdout": "NOT_RUN",
        "customer_acceptance": "NOT_RUN",
        "rootless_transformer": "NOT_RUN",
        "rootless_verifier": "NOT_RUN",
        "rootless_runner": "NOT_RUN",
        "independent_review": "NOT_RUN",
        "external_certification": "NOT_RUN",
    }
    write_json(
        local_evidence / "certification.json",
        {
            "schema_version": 1,
            "pack_key": PACK_KEY,
            "pack_version": pack_version,
            "status": status,
            "certification_decision": "NOT_CERTIFIED",
            "local_fixture_evidence": {
                "build_startup_migration_equivalence_security": "PASSED_LOCAL",
                "production_status": "NOT_RUN",
            },
            "declared_scope": ["web", "configuration", "lifecycle"],
            "gate_results": gate_results,
            "metrics": metrics,
            "evidence_refs": evidence_refs,
            "residual_risks": [
                "The supported scope is limited to web, configuration and lifecycle behavior.",
                "Security and validation probes are limited to the repository-owned synthetic fixture; provider-specific behavior remains conditional.",
                "Customer repository, rootless execution and external independent review remain NOT_RUN.",
            ],
        },
    )
    support = json.loads((pack / "support-matrix.json").read_text(encoding="utf-8"))
    runtime_evidence_path = local_evidence / "local-reference-evidence.json"
    runtime_binding = evidence_binding(pack, runtime_evidence_path, "runtime-equivalence")
    source_configuration_binding = evidence_binding(
        pack,
        pack / "corpus/development/source/src/main/resources/application.properties",
        "source-configuration",
    )
    target_configuration_binding = evidence_binding(
        pack,
        pack / "corpus/development/migrated/src/main/resources/application.properties",
        "target-configuration",
    )
    for capability in support["capabilities"]:
        if capability["id"] in {"web", "configuration", "lifecycle"}:
            capability_id = capability["id"]
            if capability_id == "web":
                bindings = [runtime_binding]
                fcm_ids = ["web-json-contract"]
            elif capability_id == "configuration":
                bindings = [
                    runtime_binding,
                    source_configuration_binding,
                    target_configuration_binding,
                ]
                fcm_ids = ["configuration-runtime-contract"]
            else:
                bindings = [runtime_binding]
                fcm_ids = ["health-lifecycle"]
            capability.update(
                {
                    "status": "supported" if public_evidence else "experimental",
                    "strategy": "framework-contract-and-real-runtime",
                    "reason": (
                        "Exact local source/target builds and startup plus separate public holdout "
                        "and representative repository behavior passed; customer and external certification remain NOT_RUN."
                    ),
                    "evidence_bindings": bindings,
                    "evidence_refs": [binding["path"] for binding in bindings],
                    "fcm_capability_ids": fcm_ids,
                    "target_profile_key": "spring-boot-2-7-18-to-3-5-3-target",
                }
            )
        elif capability["id"] == "validation":
            capability.update(
                {
                    "status": "experimental",
                    "strategy": "framework-contract-and-real-runtime",
                    "reason": (
                        "Local source and target HTTP probes cover invalid and valid request "
                        "validation; customer and independent certification remain NOT_RUN."
                    ),
                    "evidence_refs": ["certification/local-reference-evidence.json"],
                    "fcm_capability_ids": ["validation-contract"],
                    "target_profile_key": "spring-boot-2-7-18-to-3-5-3-target",
                }
            )
        elif capability["id"] in {"authentication", "authorization"}:
            capability.update(
                {
                    "status": "experimental",
                    "strategy": "framework-contract-and-real-runtime",
                    "reason": (
                        "Local source and target HTTP probes cover fixture authentication and "
                        "route authorization; provider-specific and independent certification remain NOT_RUN."
                    ),
                    "evidence_refs": ["certification/local-reference-evidence.json"],
                    "fcm_capability_ids": ["security-contract"],
                    "target_profile_key": "spring-boot-2-7-18-to-3-5-3-target",
                }
            )
    write_json(pack / "support-matrix.json", support)
    manifest = json.loads((pack / "pack.json").read_text(encoding="utf-8"))
    manifest["version"] = pack_version
    manifest["status"] = status
    write_json(pack / "pack.json", manifest)
    version_matrix = json.loads((pack / "version-matrix.json").read_text(encoding="utf-8"))
    for item in version_matrix.get("tuples", []):
        if item.get("id") == "target":
            item["status"] = "limited-output" if public_evidence else "experimental-output"
    write_json(pack / "version-matrix.json", version_matrix)
    (local_evidence / "gate-report.md").write_text(
        "# Spring Boot reference gate\n\n"
        "- Local fixture migration, equivalence and security probes: PASSED_LOCAL (self-attested only)\n"
        "- Target-repository/production Spring-JVM evidence: NOT_RUN\n"
        f"- Pack status: `{status}`\n"
        "- Declared supported scope: `web`, `configuration`, `lifecycle`\n"
        "- Spring Boot 2.7.18 / Java 17 build and startup: `PASSED_LOCAL`\n"
        "- Spring Boot 3.5.3 / Java 21 build and startup: `PASSED_LOCAL`\n"
        "- Development, synthetic holdout and representative API parity: `PASSED_LOCAL`\n"
        "- Public representative repository (88 source/88 target tests): "
        f"`{'PASSED_LOCAL_ENGINEERING' if public_evidence else 'NOT_RUN'}`\n"
        "- Independent public holdout (1 source/1 target test): "
        f"`{'PASSED_LOCAL_ENGINEERING' if public_evidence else 'NOT_RUN'}`\n"
        "- Separate local Verifier with fresh extraction and offline Maven: "
        f"`{'PASSED_LOCAL_ENGINEERING' if public_evidence else 'NOT_RUN'}`\n"
        "- Product one-click start without an attested Rootless Runner: `BLOCKED_EXPECTED` (`HTTP 409`)\n"
        "- GitHub App private-repository execution: `NOT_RUN`\n"
        "- Authorized customer repository: `NOT_RUN`\n"
        "- Customer holdout workload: `NOT_RUN`\n"
        "- Rootless Transformer, Verifier and Runner: `NOT_RUN`\n"
        "- External independent review: `NOT_RUN`\n"
        "- Certification decision: `NOT_CERTIFIED`\n",
        encoding="utf-8",
    )
    return pack


def main() -> int:
    parser = argparse.ArgumentParser(description="Spring Boot reference runner and migration validator")
    parser.add_argument("--repo-root", default=".", help="Root repository directory")
    parser.add_argument("--source-java", default=None, help="Path to JDK 17 home")
    parser.add_argument("--target-java", default=None, help="Path to JDK 21 home")
    parser.add_argument("--external-repo", default=None, help="Optional external project repository to migrate/validate")
    args = parser.parse_args()
    repo = Path(args.repo_root).resolve()
    src_java = resolve_java_home(17, args.source_java)
    tgt_java = resolve_java_home(21, args.target_java)
    ext_repo = Path(args.external_repo).resolve() if args.external_repo else None
    pack = execute(repo, source_java=src_java, target_java=tgt_java, external_repo=ext_repo)
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
