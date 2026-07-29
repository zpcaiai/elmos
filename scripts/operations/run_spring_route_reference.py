#!/usr/bin/env python3
"""Execute one declared Spring route end to end and record what actually happened.

Three of the five routes in ``SpringRouteCatalog`` carry ``NOT_RUN``. They are not
missing code -- each ships a real OpenRewrite recipe -- they are missing an
execution. ``scripts/batch30/run_spring_boot_reference.py`` produced the one
recording that does exist, but it is hard-wired to Boot 2.7.18 on Java 17.

Copying that script per route does not work, and the reasons are specific:

* The Java 8 fixture cannot use ``record`` (Java 16+) or ``Map.of`` (Java 9+),
  and Boot 1.5's ``spring-boot-starter-test`` ships JUnit 4, not Jupiter.
* Boot 1.5's actuator serves health at ``/health``; ``/actuator/health`` and the
  ``management.endpoints.web.exposure.include`` property are both Boot 2.
* Boot 1.5 has no separate ``spring-boot-starter-validation``; the validator
  arrives with ``spring-boot-starter-web``.
* A Boot 3.0-3.4 source is already on the jakarta baseline, so its fixture must
  import ``jakarta.validation``, not ``javax.validation``.

Each route therefore carries its own legacy source, and the health probe path is
a per-route property rather than a constant.

The recipe is read from the engine's own resources
(``apps/java-engine-worker/src/main/resources/rewrite``) rather than from a copy
under ``framework-packs``. Evidence about a recipe the engine does not ship is
evidence about nothing.

This script records. It does not promote: on success it prints the exact
``verifiedSourceBoot`` / ``verifiedSourceJava`` pair to write into
``SpringRouteCatalog``, and leaves that edit to a human. A script that flipped
its own evidence flag would be the executor certifying itself.

Usage:
    python3 scripts/operations/run_spring_route_reference.py --route boot-1.5-java-8-maven-to-boot-3.5.3-java-21
    python3 scripts/operations/run_spring_route_reference.py --list
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REWRITE_PLUGIN = "6.44.0"
REWRITE_SPRING = "6.35.0"
TARGET_BOOT = "3.5.3"
TARGET_JAVA = "21"
REQUIRED_MAVEN = "Apache Maven 3.9.11"

# The identifier probed against both builds. Any value works; 42 keeps the
# recorded responses comparable with the existing 2.7.18 evidence.
PROBE_IDS = [42, 7, 1001]


# --------------------------------------------------------------------------
# Legacy source variants
#
# Every variant must expose the same two endpoints with byte-identical JSON
# semantics, because the run asserts parity between the source and the migrated
# build. What differs is only what the source language level and framework
# generation actually permit.
# --------------------------------------------------------------------------

_APPLICATION = """package io.elmos.reference;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReferenceApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReferenceApplication.class, args);
    }
}
"""

# Java 8 / Boot 1.5: no records, no Map.of, no var. LinkedHashMap keeps the
# response order stable, though parity is compared on parsed objects so order is
# not load bearing.
#
# The constraint is @NotNull + @Size rather than @NotBlank on purpose. @NotBlank
# entered javax.validation.constraints only with Bean Validation 2.0 (JSR 380);
# Boot 1.5 ships Bean Validation 1.1, where the annotation exists solely as
# Hibernate Validator's own org.hibernate.validator.constraints.NotBlank. Using
# the Hibernate one would be the authentic 1.5 idiom, but it was removed in
# Hibernate Validator 7, so whether this fixture builds at the target would then
# depend on the recipe rewriting that specific annotation -- turning a route
# check into a single-annotation test. @NotNull and @Size exist unchanged in
# both generations and only need the javax -> jakarta package rename, which the
# Boot 3 migration definitively performs.
#
# Known gap this deliberately does not cover: real Boot 1.5 estates do use
# org.hibernate.validator.constraints.NotBlank, and nothing here proves the
# recipe migrates it. That deserves its own case once the route itself is
# recorded.
_CONTROLLER_JAVA8 = """package io.elmos.reference;

import java.util.LinkedHashMap;
import java.util.Map;
import javax.validation.Valid;
import javax.validation.constraints.NotNull;
import javax.validation.constraints.Size;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {
    @GetMapping("/{id}")
    Map<String, Object> find(@PathVariable long id) {
        Map<String, Object> body = new LinkedHashMap<String, Object>();
        body.put("id", id);
        body.put("status", id % 2 == 0 ? "READY" : "REVIEW");
        body.put("amountCents", Math.multiplyExact(id, 125L));
        return body;
    }

    @PostMapping
    Map<String, String> create(@Valid @RequestBody CreateOrder request) {
        Map<String, String> body = new LinkedHashMap<String, String>();
        body.put("customerId", request.getCustomerId());
        body.put("status", "CREATED");
        return body;
    }

    public static class CreateOrder {
        @NotNull
        @Size(min = 1)
        private String customerId;

        public String getCustomerId() {
            return customerId;
        }

        public void setCustomerId(String customerId) {
            this.customerId = customerId;
        }
    }
}
"""

# Java 11: Map.of is available, records are not (Java 16+).
_CONTROLLER_JAVA11 = """package io.elmos.reference;

import java.util.Map;
import javax.validation.Valid;
import javax.validation.constraints.NotBlank;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
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
        return Map.of("customerId", request.getCustomerId(), "status", "CREATED");
    }

    public static class CreateOrder {
        @NotBlank
        private String customerId;

        public String getCustomerId() {
            return customerId;
        }

        public void setCustomerId(String customerId) {
            this.customerId = customerId;
        }
    }
}
"""

# Boot 3.x source: already on the jakarta baseline before any migration runs.
_CONTROLLER_JAKARTA = """package io.elmos.reference;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
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

# Boot 1.5 ships JUnit 4; @SpringRunner plus @SpringBootTest is the idiomatic
# 1.5 web slice.
_TEST_JUNIT4 = """package io.elmos.reference;

import static org.hamcrest.Matchers.is;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.Test;
import org.junit.runner.RunWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.junit4.SpringRunner;
import org.springframework.test.web.servlet.MockMvc;

@RunWith(SpringRunner.class)
@SpringBootTest
@AutoConfigureMockMvc
public class OrderControllerTest {
    @Autowired
    private MockMvc mvc;

    @Test
    public void preservesOrderContract() throws Exception {
        mvc.perform(get("/api/orders/42"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id", is(42)))
            .andExpect(jsonPath("$.status", is("READY")))
            .andExpect(jsonPath("$.amountCents", is(5250)));
    }
}
"""

_TEST_JUNIT5 = """package io.elmos.reference;

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

# Boot 1.5's actuator predates the /actuator prefix and the exposure property.
_PROPERTIES_BOOT1 = """endpoints.health.sensitive=false
endpoints.enabled=false
endpoints.health.enabled=true
"""

_PROPERTIES_BOOT2_PLUS = """management.endpoints.web.exposure.include=health
management.endpoint.health.show-details=never
server.shutdown=graceful
"""


@dataclass(frozen=True)
class Route:
    route_id: str
    recipe_file: str
    recipe_id: str
    source_boot: str
    source_java: str
    controller: str
    test: str
    properties: str
    health_path: str
    # Boot 1.5 has no standalone validation starter; the validator ships with web.
    extra_starters: tuple[str, ...] = field(default=("validation",))


ROUTES: dict[str, Route] = {
    "boot-1.5-java-8-maven-to-boot-3.5.3-java-21": Route(
        route_id="boot-1.5-java-8-maven-to-boot-3.5.3-java-21",
        recipe_file="spring-boot-1.5-to-3.5.3.yml",
        recipe_id="io.elmos.openrewrite.SpringBoot1_5ToBoot3_5_3Java21",
        source_boot="1.5.22.RELEASE",
        source_java="8",
        controller=_CONTROLLER_JAVA8,
        test=_TEST_JUNIT4,
        properties=_PROPERTIES_BOOT1,
        health_path="/health",
        extra_starters=(),
    ),
    "boot-2.0-2.6-maven-to-boot-3.5.3-java-21": Route(
        route_id="boot-2.0-2.6-maven-to-boot-3.5.3-java-21",
        recipe_file="spring-boot-2.0-2.6-to-3.5.3.yml",
        recipe_id="io.elmos.openrewrite.SpringBoot2_0To2_6ToBoot3_5_3Java21",
        source_boot="2.3.12.RELEASE",
        source_java="11",
        controller=_CONTROLLER_JAVA11,
        test=_TEST_JUNIT5,
        properties=_PROPERTIES_BOOT2_PLUS,
        health_path="/actuator/health",
    ),
    "boot-3.0-3.4-maven-to-boot-3.5.3-java-21": Route(
        route_id="boot-3.0-3.4-maven-to-boot-3.5.3-java-21",
        recipe_file="spring-boot-3.0-3.4-to-3.5.3.yml",
        recipe_id="io.elmos.openrewrite.SpringBoot3_0To3_4ToBoot3_5_3Java21",
        source_boot="3.4.1",
        source_java="17",
        controller=_CONTROLLER_JAKARTA,
        test=_TEST_JUNIT5,
        properties=_PROPERTIES_BOOT2_PLUS,
        health_path="/actuator/health",
    ),
    # The already-recorded route is included so the harness can be re-run against
    # a known-good tuple. If this one stops passing, the harness is wrong, not
    # the three new routes.
    "boot-2.7-maven-to-boot-3.5.3-java-21": Route(
        route_id="boot-2.7-maven-to-boot-3.5.3-java-21",
        recipe_file="spring-boot-2.7.18-to-3.5.3.yml",
        recipe_id="io.elmos.openrewrite.SpringBoot2_7_18To3_5_3Java21",
        source_boot="2.7.18",
        source_java="17",
        controller=_CONTROLLER_JAVA11,
        test=_TEST_JUNIT5,
        properties=_PROPERTIES_BOOT2_PLUS,
        health_path="/actuator/health",
    ),
}


class RunFailure(RuntimeError):
    """A named failure, so the caller learns which stage refused."""


def reports_release(version_output: str, release: str) -> bool:
    """Does ``java -version`` output describe the requested release?

    Java 8 and earlier report the legacy ``1.8.0_432`` form; 9 onwards report
    ``21.0.11``. Both schemes appear in a legacy estate, so both are accepted --
    but ``1.21`` is not a Java 21, so the legacy form is only honoured up to 8.
    """
    for quoted in re.findall(r'"([^"]+)"', version_output or ""):
        if quoted.startswith("1."):
            legacy = quoted.split(".")
            if len(legacy) > 1 and legacy[1].isdigit() and int(legacy[1]) <= 8:
                if legacy[1] == release:
                    return True
            continue
        head = quoted.split(".")[0]
        if head.isdigit() and head == release:
            return True
    return False


def java_home(release: str) -> Path:
    """Locate a JDK for ``release`` and confirm it really is that release.

    An explicit ``ELMOS_JAVA_<n>_HOME`` always wins; on macOS the system
    ``java_home`` tool is consulted next.

    The result is then verified by running ``java -version``, because resolving
    and trusting is not the same as resolving. A wrong toolchain does not fail
    where it was chosen -- it fails much later and in a way that looks like a
    migration defect. Building the Boot 1.5 fixture under a modern JDK, for
    instance, surfaces as Spring 4.3's cglib hitting JPMS strong encapsulation
    ("module java.base does not open java.lang"), which reads like a broken
    recipe and is nothing of the sort. Naming the real problem here costs one
    subprocess call.
    """
    override = os.environ.get(f"ELMOS_JAVA_{release}_HOME")
    if override:
        candidate = Path(override)
        source = f"ELMOS_JAVA_{release}_HOME"
    elif platform.system() == "Darwin" and Path("/usr/libexec/java_home").is_file():
        found = subprocess.run(
            ["/usr/libexec/java_home", "-v", release],
            text=True, capture_output=True, check=False,
        )
        if found.returncode != 0 or not found.stdout.strip():
            raise RunFailure(
                f"JAVA_{release}_MISSING\n"
                f"  /usr/libexec/java_home -v {release} found no JDK.\n"
                f"  Install one (e.g. brew install --cask temurin@{release}) or set "
                f"ELMOS_JAVA_{release}_HOME.")
        candidate = Path(found.stdout.strip())
        source = f"/usr/libexec/java_home -v {release}"
    else:
        raise RunFailure(
            f"JAVA_{release}_MISSING: set ELMOS_JAVA_{release}_HOME to a JDK {release} home")

    if not (candidate / "bin/java").is_file():
        raise RunFailure(f"JAVA_HOME_INVALID:{source} -> {candidate} has no bin/java")

    probe = subprocess.run(
        [str(candidate / "bin/java"), "-version"],
        text=True, capture_output=True, check=False,
    )
    # `java -version` writes to stderr on every JDK that matters here.
    reported = (probe.stderr or "") + (probe.stdout or "")
    if not reports_release(reported, release):
        raise RunFailure(
            f"JAVA_{release}_TOOLCHAIN_MISMATCH\n"
            f"  resolved via: {source}\n"
            f"  home:         {candidate}\n"
            f"  reports:      {reported.splitlines()[0] if reported.strip() else '<no output>'}\n"
            f"  required:     Java {release}\n"
            "\n"
            f"Set ELMOS_JAVA_{release}_HOME to a real JDK {release} home. Running the "
            "source build on the wrong JDK does not produce a wrong answer -- it "
            "produces a plausible-looking failure somewhere else entirely.")
    return candidate


def run(
    command: list[str],
    *,
    cwd: Path,
    home: Path,
    timeout: int = 1_800,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["JAVA_HOME"] = str(home)
    environment["PATH"] = f"{home / 'bin'}:{environment.get('PATH', '')}"
    for key in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY",
                "https_proxy", "http_proxy", "all_proxy"):
        environment.pop(key, None)
    environment["NO_PROXY"] = "repo.maven.apache.org,localhost,127.0.0.1"
    environment["no_proxy"] = environment["NO_PROXY"]
    completed = subprocess.run(
        command, cwd=cwd, env=environment, text=True,
        capture_output=True, check=False, timeout=timeout,
    )
    if completed.returncode != 0:
        tail = (completed.stdout + completed.stderr)[-8_000:]
        raise RunFailure(f"COMMAND_FAILED:{' '.join(command)}\n{tail}")
    return completed


def pom(route: Route) -> str:
    starters = "".join(
        f"""
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-{name}</artifactId>
    </dependency>"""
        for name in ("web", "actuator", *route.extra_starters)
    )
    artifact = "spring-reference-" + route.source_boot.replace(".", "-").lower()
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>{route.source_boot}</version>
    <relativePath/>
  </parent>
  <groupId>io.elmos</groupId>
  <artifactId>{artifact}</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>{route.source_java}</java.version>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>{starters}
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


def materialize(project: Path, route: Route) -> None:
    if project.exists():
        shutil.rmtree(project)
    source = project / "src/main/java/io/elmos/reference"
    tests = project / "src/test/java/io/elmos/reference"
    resources = project / "src/main/resources"
    for directory in (source, tests, resources):
        directory.mkdir(parents=True, exist_ok=True)
    (project / "pom.xml").write_text(pom(route), encoding="utf-8")
    (source / "ReferenceApplication.java").write_text(_APPLICATION, encoding="utf-8")
    (source / "OrderController.java").write_text(route.controller, encoding="utf-8")
    (tests / "OrderControllerTest.java").write_text(route.test, encoding="utf-8")
    (resources / "application.properties").write_text(route.properties, encoding="utf-8")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


def request_json(port: int, path: str, *, timeout: float = 2.0) -> dict[str, Any]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        connection.request("GET", path, headers={"Accept": "application/json"})
        response = connection.getresponse()
        if response.status != 200:
            raise RunFailure(f"HTTP_{response.status}:{path}")
        return json.loads(response.read())
    finally:
        connection.close()


def start_and_probe(
    project: Path, *, home: Path, health_path: str, log_path: Path
) -> dict[str, Any]:
    jar = next(
        path for path in sorted((project / "target").glob("*.jar"))
        if not path.name.endswith(".original")
    )
    port = free_port()
    environment = os.environ.copy()
    environment["JAVA_HOME"] = str(home)
    environment["PATH"] = f"{home / 'bin'}:{environment.get('PATH', '')}"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            [str(home / "bin/java"), "-jar", str(jar),
             f"--server.port={port}", "--server.address=127.0.0.1"],
            cwd=project, env=environment, stdin=subprocess.DEVNULL,
            stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 120
            health: dict[str, Any] | None = None
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    break
                try:
                    health = request_json(port, health_path)
                    break
                except (OSError, http.client.HTTPException, json.JSONDecodeError, RunFailure):
                    time.sleep(0.25)
            if health is None or health.get("status") != "UP":
                tail = log_path.read_text(encoding="utf-8", errors="replace")[-8_000:]
                raise RunFailure(f"STARTUP_FAILED:{project.name}\n{tail}")
            return {
                "health": health,
                "responses": {
                    str(identifier): request_json(port, f"/api/orders/{identifier}")
                    for identifier in PROBE_IDS
                },
                "jar_sha256": hashlib.sha256(jar.read_bytes()).hexdigest(),
            }
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def transform(source: Path, target: Path, recipe: Path, route: Route, maven: str,
              home: Path) -> subprocess.CompletedProcess[str]:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target,
                    ignore=shutil.ignore_patterns("target", ".git", ".elmos"))
    installed = target / ".elmos/openrewrite.yml"
    installed.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(recipe, installed)
    result = run(
        [maven, "-B", "--no-transfer-progress",
         f"org.openrewrite.maven:rewrite-maven-plugin:{REWRITE_PLUGIN}:run",
         "-Drewrite.configLocation=.elmos/openrewrite.yml",
         f"-Drewrite.activeRecipes={route.recipe_id}",
         f"-Drewrite.recipeArtifactCoordinates=org.openrewrite.recipe:rewrite-spring:{REWRITE_SPRING}"],
        cwd=target, home=home, timeout=3_600,
    )
    if "Recipe validation error" in result.stdout + result.stderr:
        raise RunFailure("OPENREWRITE_RECIPE_VALIDATION_FAILED")
    text = (target / "pom.xml").read_text(encoding="utf-8")
    if f"<version>{TARGET_BOOT}</version>" not in text:
        raise RunFailure("OPENREWRITE_TARGET_BOOT_BINDING_FAILED")
    if f"<java.version>{TARGET_JAVA}</java.version>" not in text:
        raise RunFailure("OPENREWRITE_TARGET_JAVA_BINDING_FAILED")
    return result


def execute(repo: Path, route: Route, workspace: Path) -> dict[str, Any]:
    recipe = (repo / "apps/java-engine-worker/src/main/resources/rewrite"
              / route.recipe_file)
    if not recipe.is_file():
        raise RunFailure(f"RECIPE_MISSING:{recipe}")

    maven = os.environ.get("ELMOS_MAVEN_EXECUTABLE") or shutil.which("mvn")
    if maven is None or not Path(maven).is_file():
        raise RunFailure("MAVEN_MISSING")

    source_home = java_home(route.source_java)
    target_home = java_home(TARGET_JAVA)

    version_line = run([maven, "-version"], cwd=repo, home=target_home,
                       timeout=120).stdout.splitlines()[0]
    if REQUIRED_MAVEN not in version_line:
        # Not pedantry: SpringRouteCatalog.MAVEN_TOOLCHAIN bakes "maven-3.9.11"
        # into the ExactTuple the engine reports to customers, and the existing
        # 2.7.18 evidence was produced on that version. Recording a pass from a
        # different Maven would make the catalog name a toolchain that never ran
        # and would make the routes incomparable with each other.
        raise RunFailure(
            f"EXACT_MAVEN_VERSION_REQUIRED\n"
            f"  found:    {version_line}\n"
            f"  required: {REQUIRED_MAVEN}\n"
            f"  at:       {maven}\n"
            "\n"
            "Install it side by side and point the harness at it:\n"
            "  curl -fsSLO https://archive.apache.org/dist/maven/maven-3/3.9.11/"
            "binaries/apache-maven-3.9.11-bin.tar.gz\n"
            "  mkdir -p ~/.local/maven && tar -xzf apache-maven-3.9.11-bin.tar.gz "
            "-C ~/.local/maven\n"
            "  export ELMOS_MAVEN_EXECUTABLE=$HOME/.local/maven/"
            "apache-maven-3.9.11/bin/mvn\n"
            "\n"
            "Do not relax this check to match the Maven you happen to have. The "
            "version is part of the tuple the engine reports.")

    source = workspace / "source"
    target = workspace / "migrated"
    logs = workspace / "logs"

    materialize(source, route)
    source_build = run([maven, "-B", "--no-transfer-progress", "verify"],
                       cwd=source, home=source_home)
    transformation = transform(source, target, recipe, route, maven, target_home)
    target_build = run([maven, "-B", "--no-transfer-progress", "verify"],
                       cwd=target, home=target_home)

    source_runtime = start_and_probe(
        source, home=source_home, health_path=route.health_path,
        log_path=logs / "source-runtime.log")
    target_runtime = start_and_probe(
        target, home=target_home, health_path="/actuator/health",
        log_path=logs / "target-runtime.log")

    if source_runtime["responses"] != target_runtime["responses"]:
        raise RunFailure(
            "FRAMEWORK_BEHAVIOR_DIFFERENCE\n"
            f"source={json.dumps(source_runtime['responses'], sort_keys=True)}\n"
            f"target={json.dumps(target_runtime['responses'], sort_keys=True)}")

    return {
        "schema_version": 1,
        "route_id": route.route_id,
        "execution_status": "PASSED_LOCAL",
        "recorded_tuple": {
            "source_boot": route.source_boot,
            "source_java": route.source_java,
            "target_boot": TARGET_BOOT,
            "target_java": TARGET_JAVA,
        },
        "source": {
            "boot": route.source_boot,
            "java": run(["java", "-version"], cwd=source, home=source_home,
                        timeout=120).stderr.splitlines()[0],
            "health_path": route.health_path,
            "build": "PASSED",
            "build_tail": source_build.stdout[-2_000:],
            "runtime": source_runtime,
        },
        "target": {
            "boot": TARGET_BOOT,
            "java": run(["java", "-version"], cwd=target, home=target_home,
                        timeout=120).stderr.splitlines()[0],
            "health_path": "/actuator/health",
            "build": "PASSED",
            "build_tail": target_build.stdout[-2_000:],
            "runtime": target_runtime,
        },
        "transformation": {
            "engine": "OpenRewrite",
            "recipe_id": route.recipe_id,
            "recipe_path": str(recipe.relative_to(repo)),
            "recipe_sha256": hashlib.sha256(recipe.read_bytes()).hexdigest(),
            "maven": version_line,
            "rewrite_maven_plugin": REWRITE_PLUGIN,
            "rewrite_spring": REWRITE_SPRING,
            "output_tail": transformation.stdout[-2_000:],
        },
        "behavioral_parity": True,
        "probe_ids": PROBE_IDS,
        # Everything below stays NOT_RUN. A local pass is a local pass.
        "authorized_customer_repository": "NOT_RUN",
        "rootless_runner": "NOT_RUN",
        "independent_verification": "NOT_RUN",
        "external_evidence_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route", help="route id from SpringRouteCatalog")
    parser.add_argument("--list", action="store_true", help="list runnable routes")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--workspace",
                        help="where the fixtures are built (default: a temp dir)")
    args = parser.parse_args()

    if args.list:
        for route_id, route in ROUTES.items():
            print(f"{route_id}\n    source: Boot {route.source_boot} / Java "
                  f"{route.source_java}   health: {route.health_path}")
        return 0
    if not args.route:
        parser.error("--route is required (or use --list)")
    if args.route not in ROUTES:
        print(f"UNKNOWN_ROUTE:{args.route}", file=sys.stderr)
        print("known routes:", *ROUTES, sep="\n  ", file=sys.stderr)
        return 2

    repo = Path(args.repo_root).resolve()
    route = ROUTES[args.route]
    workspace = Path(args.workspace).resolve() if args.workspace else (
        repo / "build/spring-route-reference" / route.route_id)
    workspace.mkdir(parents=True, exist_ok=True)

    destination = repo / "evidence/spring-routes" / f"{route.route_id}.json"
    try:
        evidence = execute(repo, route, workspace)
    except RunFailure as failure:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps({
            "schema_version": 1,
            "route_id": route.route_id,
            "execution_status": "FAILED",
            "failure": str(failure),
        }, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"FAIL: {route.route_id}\n{failure}", file=sys.stderr)
        print(f"recorded at {destination}", file=sys.stderr)
        return 1

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")

    print(f"PASS: {route.route_id}")
    print(f"evidence: {destination}")
    print()
    print("This run does not promote the route by itself. To record it, edit")
    print("apps/java-engine-worker/src/main/java/io/elmos/worker/SpringRouteCatalog.java")
    print(f"for route {route.route_id} and set:")
    print(f"    EvidenceStatus.PASSED_LOCAL, \"{route.source_boot}\", \"{route.source_java}\"")
    print()
    print("Note: SpringRouteCatalogTest.exactlyOneRouteCarriesRecordedEvidence")
    print("pins the catalog to a single verified route. Promoting a second one")
    print("must update that test deliberately, not incidentally.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
