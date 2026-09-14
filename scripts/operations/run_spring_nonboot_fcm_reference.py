#!/usr/bin/env python3
"""Run exact non-Boot Spring/MVC fixtures through an FCM target generator.

This is a bounded local executor. It validates one admitted source graph,
materializes a fresh Boot target from a typed FCM, builds both sides with exact
Maven/JDK tuples, starts the source in a digest-pinned Docker runtime, and
compares observable behavior. It never promotes certification status.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import socket
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any


TOMCAT_IMAGE = "tomcat@sha256:712120b4bca129c7ac3f433f58695db5550eff499c4d435b0f8a120b41b132c6"
MAVEN_VERSION = "Apache Maven 3.9.11"
PROBE_IDS = (42, 7, 1001)


@dataclass(frozen=True)
class Route:
    route_id: str
    family: str
    source_spring: str
    target_boot: str


ROUTES = {
    route.route_id: route for route in (
        Route("spring-mvc-3.2-5.2-maven-to-boot-3.5.3-java-21", "spring-mvc", "5.2.25.RELEASE", "3.5.3"),
        Route("spring-mvc-3.2-7.0-maven-to-boot-4.1.1-java-21", "spring-mvc", "5.3.39", "4.1.1"),
        Route("spring-framework-3.2-7.0-maven-to-boot-4.1.0-java-21", "spring-framework", "5.3.39", "4.1.0"),
        Route("spring-framework-3.2-7.0-maven-to-boot-4.1.1-java-21", "spring-framework", "5.3.39", "4.1.1"),
    )
}


class Failure(RuntimeError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def run(command: list[str], cwd: Path, java_home: Path, timeout: int = 1800) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["JAVA_HOME"] = str(java_home)
    env["PATH"] = f"{java_home / 'bin'}:{env.get('PATH', '')}"
    completed = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, timeout=timeout)
    if completed.returncode:
        raise Failure(f"COMMAND_FAILED:{' '.join(command)}\n{(completed.stdout + completed.stderr)[-8000:]}")
    return completed


def maven_pom(route: Route, *, target: bool) -> str:
    if not target:
        dependency = "spring-webmvc" if route.family == "spring-mvc" else "spring-context"
        packaging = "war" if route.family == "spring-mvc" else "jar"
        servlet = "" if route.family != "spring-mvc" else """
    <dependency><groupId>javax.servlet</groupId><artifactId>javax.servlet-api</artifactId><version>4.0.1</version><scope>provided</scope></dependency>
    <dependency><groupId>com.fasterxml.jackson.core</groupId><artifactId>jackson-databind</artifactId><version>2.17.2</version></dependency>"""
        shade = "" if route.family == "spring-mvc" else """
      <plugin><groupId>org.apache.maven.plugins</groupId><artifactId>maven-shade-plugin</artifactId><version>3.6.0</version><executions><execution><phase>package</phase><goals><goal>shade</goal></goals><configuration><createDependencyReducedPom>false</createDependencyReducedPom><transformers><transformer implementation="org.apache.maven.plugins.shade.resource.AppendingTransformer"><resource>META-INF/spring.handlers</resource></transformer><transformer implementation="org.apache.maven.plugins.shade.resource.AppendingTransformer"><resource>META-INF/spring.schemas</resource></transformer><transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer"><mainClass>io.elmos.reference.SourceApplication</mainClass></transformer></transformers></configuration></execution></executions></plugin>"""
        return f"""<project xmlns="http://maven.apache.org/POM/4.0.0"><modelVersion>4.0.0</modelVersion>
  <groupId>io.elmos.reference</groupId><artifactId>nonboot-source</artifactId><version>1.0.0</version><packaging>{packaging}</packaging>
  <properties><maven.compiler.release>11</maven.compiler.release><project.build.sourceEncoding>UTF-8</project.build.sourceEncoding></properties>
  <dependencies><dependency><groupId>org.springframework</groupId><artifactId>{dependency}</artifactId><version>{route.source_spring}</version></dependency>{servlet}</dependencies>
  <build><finalName>nonboot-source</finalName><plugins><plugin><groupId>org.apache.maven.plugins</groupId><artifactId>maven-compiler-plugin</artifactId><version>3.13.0</version></plugin><plugin><groupId>org.apache.maven.plugins</groupId><artifactId>maven-war-plugin</artifactId><version>3.4.0</version><configuration><failOnMissingWebXml>false</failOnMissingWebXml></configuration></plugin>{shade}</plugins></build>
</project>"""
    starter = "spring-boot-starter-web" if route.target_boot.startswith("3.") else "spring-boot-starter-webmvc"
    web_dependencies = "" if route.family != "spring-mvc" else f"""
    <dependency><groupId>org.springframework.boot</groupId><artifactId>{starter}</artifactId></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-actuator</artifactId></dependency>"""
    core_dependency = "" if route.family == "spring-mvc" else "<dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter</artifactId></dependency>"
    return f"""<project xmlns="http://maven.apache.org/POM/4.0.0"><modelVersion>4.0.0</modelVersion>
  <parent><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-parent</artifactId><version>{route.target_boot}</version><relativePath/></parent>
  <groupId>io.elmos.reference</groupId><artifactId>fcm-target</artifactId><version>1.0.0</version>
  <properties><java.version>21</java.version><maven.compiler.release>21</maven.compiler.release></properties>
  <dependencies>{web_dependencies}{core_dependency}</dependencies>
  <build><plugins><plugin><groupId>org.springframework.boot</groupId><artifactId>spring-boot-maven-plugin</artifactId><version>{route.target_boot}</version><executions><execution><goals><goal>repackage</goal></goals></execution></executions></plugin></plugins></build>
</project>"""


ORDER_SERVICE = """package io.elmos.reference;
import java.util.LinkedHashMap; import java.util.Map;
public class OrderService {
  private String currency = "CNY"; private long multiplier = 125L;
  public void setCurrency(String value) { currency = value; }
  public void setMultiplier(long value) { multiplier = value; }
  public Map<String,Object> find(long id) { Map<String,Object> value = new LinkedHashMap<>(); value.put("id", id); value.put("status", id % 2 == 0 ? "READY" : "REVIEW"); value.put("amountCents", Math.multiplyExact(id, multiplier)); value.put("currency", currency); return value; }
}
"""


CONTROLLER = """package io.elmos.reference;
import java.util.Map; import org.springframework.web.bind.annotation.*;
@RestController @RequestMapping("/api/orders")
public class OrderController { private final OrderService service; public OrderController(OrderService service) { this.service = service; }
  @GetMapping("/{id}") public Map<String,Object> find(@PathVariable long id) { return service.find(id); }
}
"""


def materialize_source(root: Path, route: Route) -> None:
    write(root / "pom.xml", maven_pom(route, target=False))
    write(root / "src/main/java/io/elmos/reference/OrderService.java", ORDER_SERVICE)
    if route.family == "spring-mvc":
        write(root / "src/main/java/io/elmos/reference/OrderController.java", CONTROLLER)
        write(root / "src/main/webapp/WEB-INF/web.xml", """<web-app xmlns="http://xmlns.jcp.org/xml/ns/javaee" version="4.0"><servlet><servlet-name>dispatcher</servlet-name><servlet-class>org.springframework.web.servlet.DispatcherServlet</servlet-class><init-param><param-name>contextConfigLocation</param-name><param-value>classpath:/application-context.xml</param-value></init-param><load-on-startup>1</load-on-startup></servlet><servlet-mapping><servlet-name>dispatcher</servlet-name><url-pattern>/</url-pattern></servlet-mapping></web-app>""")
        write(root / "src/main/resources/application-context.xml", """<beans xmlns="http://www.springframework.org/schema/beans" xmlns:mvc="http://www.springframework.org/schema/mvc" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.springframework.org/schema/beans http://www.springframework.org/schema/beans/spring-beans.xsd http://www.springframework.org/schema/mvc http://www.springframework.org/schema/mvc/spring-mvc.xsd"><mvc:annotation-driven/><bean id="orderService" class="io.elmos.reference.OrderService"><property name="currency" value="CNY"/><property name="multiplier" value="125"/></bean><bean class="io.elmos.reference.OrderController"><constructor-arg ref="orderService"/></bean></beans>""")
    else:
        write(root / "src/main/java/io/elmos/reference/SourceApplication.java", """package io.elmos.reference;
import org.springframework.context.support.ClassPathXmlApplicationContext;
public class SourceApplication { public static void main(String[] args) { try (ClassPathXmlApplicationContext context = new ClassPathXmlApplicationContext("application-context.xml")) { OrderService service = context.getBean(OrderService.class); for (long id : new long[]{42,7,1001}) System.out.println("ELMOS_RESULT=" + id + ":" + service.find(id)); } } }
""")
        write(root / "src/main/resources/application-context.xml", """<beans xmlns="http://www.springframework.org/schema/beans" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.springframework.org/schema/beans http://www.springframework.org/schema/beans/spring-beans.xsd"><bean id="orderService" class="io.elmos.reference.OrderService"><property name="currency" value="CNY"/><property name="multiplier" value="125"/></bean></beans>""")


def extract_fcm(source: Path, route: Route) -> dict[str, Any]:
    pom = ET.parse(source / "pom.xml").getroot()
    dependencies = [(node.findtext("{*}groupId"), node.findtext("{*}artifactId"), node.findtext("{*}version")) for node in pom.findall(".//{*}dependency")]
    expected = "spring-webmvc" if route.family == "spring-mvc" else "spring-context"
    if ("org.springframework", expected, route.source_spring) not in dependencies:
        raise Failure("FCM_SOURCE_DEPENDENCY_MISMATCH")
    context = ET.parse(source / "src/main/resources/application-context.xml").getroot()
    beans = [node for node in context.findall("{http://www.springframework.org/schema/beans}bean")]
    order = [node for node in beans if node.get("id") == "orderService"]
    if len(order) != 1 or order[0].get("class") != "io.elmos.reference.OrderService":
        raise Failure("FCM_BEAN_GRAPH_MISMATCH")
    properties = {node.get("name"): node.get("value") for node in order[0].findall("{http://www.springframework.org/schema/beans}property")}
    if properties != {"currency": "CNY", "multiplier": "125"}:
        raise Failure("FCM_PROPERTY_GRAPH_MISMATCH")
    if route.family == "spring-mvc":
        web = ET.parse(source / "src/main/webapp/WEB-INF/web.xml").getroot()
        mappings = [node.text for node in web.findall(".//{*}url-pattern")]
        if mappings != ["/"]:
            raise Failure("FCM_SERVLET_MAPPING_MISMATCH")
    return {"schema_version": 1, "status": "FCM_EXTRACTED_LOCAL", "route_id": route.route_id, "source": {"family": route.family, "spring": route.source_spring, "java": "11", "build": "maven-3.9.11"}, "target": {"spring_boot": route.target_boot, "java": "21", "build": "maven-3.9.11"}, "beans": [{"id": "orderService", "class": "io.elmos.reference.OrderService", "properties": properties, "lifecycle": "application-context"}], "web": {"dispatcher_mapping": "/"} if route.family == "spring-mvc" else {"mode": "non-web-context"}, "obligations": ["bean-identity", "constructor-wiring", "property-values", "context-startup", "order-response-equivalence"]}


def materialize_target(root: Path, route: Route, fcm: dict[str, Any]) -> None:
    if fcm["route_id"] != route.route_id or fcm["beans"][0]["properties"] != {"currency": "CNY", "multiplier": "125"}:
        raise Failure("FCM_TARGET_GENERATOR_INPUT_REJECTED")
    write(root / "pom.xml", maven_pom(route, target=True))
    write(root / "src/main/java/io/elmos/reference/OrderService.java", ORDER_SERVICE)
    if route.family == "spring-mvc":
        write(root / "src/main/java/io/elmos/reference/OrderController.java", CONTROLLER)
        write(root / "src/main/java/io/elmos/reference/TargetApplication.java", """package io.elmos.reference;
import org.springframework.boot.SpringApplication; import org.springframework.boot.autoconfigure.SpringBootApplication; import org.springframework.context.annotation.Bean;
@SpringBootApplication public class TargetApplication { public static void main(String[] args) { SpringApplication.run(TargetApplication.class, args); } @Bean OrderService orderService() { OrderService service = new OrderService(); service.setCurrency("CNY"); service.setMultiplier(125L); return service; } }
""")
        write(root / "src/main/resources/application.properties", "management.endpoints.web.exposure.include=health\nmanagement.endpoint.health.show-details=never\nserver.shutdown=graceful\n")
    else:
        write(root / "src/main/java/io/elmos/reference/TargetApplication.java", """package io.elmos.reference;
import org.springframework.boot.*; import org.springframework.boot.autoconfigure.SpringBootApplication; import org.springframework.context.ConfigurableApplicationContext; import org.springframework.context.annotation.Bean;
@SpringBootApplication public class TargetApplication { @Bean OrderService orderService() { OrderService service = new OrderService(); service.setCurrency("CNY"); service.setMultiplier(125L); return service; } public static void main(String[] args) { SpringApplication app = new SpringApplication(TargetApplication.class); app.setWebApplicationType(WebApplicationType.NONE); try (ConfigurableApplicationContext context = app.run(args)) { OrderService service = context.getBean(OrderService.class); for (long id : new long[]{42,7,1001}) System.out.println("ELMOS_RESULT=" + id + ":" + service.find(id)); } } }
""")
    write(root / ".elmos/framework-contract-model.json", json.dumps(fcm, indent=2, sort_keys=True) + "\n")


def free_port() -> int:
    with socket.socket() as handle:
        handle.bind(("127.0.0.1", 0)); return int(handle.getsockname()[1])


def request_json(port: int, path: str) -> dict[str, Any]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        connection.request("GET", path, headers={"Accept": "application/json"})
        response = connection.getresponse(); body = response.read()
        if response.status != 200: raise Failure(f"HTTP_{response.status}:{path}")
        return json.loads(body)
    finally: connection.close()


def wait_json(port: int, path: str) -> dict[str, Any]:
    deadline = time.monotonic() + 120; last = ""
    while time.monotonic() < deadline:
        try: return request_json(port, path)
        except Exception as exc: last = str(exc); time.sleep(.25)
    raise Failure(f"STARTUP_TIMEOUT:{path}:{last}")


def source_mvc_runtime(source: Path, log: Path) -> dict[str, Any]:
    name = f"elmos-spring-mvc-{os.getpid()}"
    port = free_port(); war = source / "target/nonboot-source.war"
    command = ["docker", "run", "-d", "--rm", "--name", name, "--platform", "linux/arm64", "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", "512", "--memory", "1g", "-p", f"127.0.0.1:{port}:8080", "-v", f"{war}:/usr/local/tomcat/webapps/ROOT.war:ro", TOMCAT_IMAGE]
    started = subprocess.run(command, text=True, capture_output=True)
    if started.returncode: raise Failure("SOURCE_CONTAINER_START_FAILED:" + started.stderr)
    try:
        responses = {str(value): wait_json(port, f"/api/orders/{value}") for value in PROBE_IDS}
        return {"container_image": TOMCAT_IMAGE, "container_id": started.stdout.strip(), "responses": responses, "loopback_port": True, "docker_boundary": "PASSED_LOCAL_NON_ROOTLESS"}
    finally:
        logs = subprocess.run(["docker", "logs", name], text=True, capture_output=True)
        log.write_text(logs.stdout + logs.stderr, encoding="utf-8")
        subprocess.run(["docker", "stop", "-t", "10", name], capture_output=True)


def parse_results(output: str) -> dict[str, str]:
    values = {}
    for line in output.splitlines():
        if line.startswith("ELMOS_RESULT="):
            key, value = line.removeprefix("ELMOS_RESULT=").split(":", 1); values[key] = value
    if set(values) != {str(value) for value in PROBE_IDS}: raise Failure("CONTEXT_RESULT_SET_INCOMPLETE")
    return values


def source_core_runtime(source: Path) -> dict[str, Any]:
    jar = source / "target/nonboot-source.jar"
    completed = subprocess.run(["docker", "run", "--rm", "--platform", "linux/arm64", "--network", "none", "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", "256", "--memory", "768m", "-v", f"{jar}:/work/app.jar:ro", "--entrypoint", "java", TOMCAT_IMAGE, "-jar", "/work/app.jar"], text=True, capture_output=True, timeout=120)
    if completed.returncode: raise Failure("SOURCE_CONTEXT_START_FAILED:" + completed.stderr)
    return {"container_image": TOMCAT_IMAGE, "results": parse_results(completed.stdout), "docker_boundary": "PASSED_LOCAL_NON_ROOTLESS", "network": "none"}


def target_runtime(target: Path, route: Route, java21: Path, log: Path) -> dict[str, Any]:
    jar = next(path for path in (target / "target").glob("*.jar") if not path.name.endswith(".original"))
    if route.family == "spring-framework":
        completed = run([str(java21 / "bin/java"), "-jar", str(jar)], target, java21, 120)
        log.write_text(completed.stdout + completed.stderr, encoding="utf-8")
        return {"results": parse_results(completed.stdout), "jar_sha256": sha256(jar)}
    port = free_port()
    with log.open("wb") as stream:
        process = subprocess.Popen([str(java21 / "bin/java"), "-jar", str(jar), f"--server.port={port}", "--server.address=127.0.0.1"], cwd=target, stdout=stream, stderr=subprocess.STDOUT)
        try:
            health = wait_json(port, "/actuator/health")
            responses = {str(value): request_json(port, f"/api/orders/{value}") for value in PROBE_IDS}
            return {"health": health, "responses": responses, "jar_sha256": sha256(jar)}
        finally:
            process.terminate()
            try: process.wait(15)
            except subprocess.TimeoutExpired: process.kill(); process.wait(5)


def execute(repo: Path, workspace: Path, route: Route) -> dict[str, Any]:
    if workspace.exists():
        if not workspace.is_dir() or any(workspace.iterdir()):
            raise Failure("WORKSPACE_MUST_BE_AN_EMPTY_DIRECTORY")
    else:
        workspace.mkdir(parents=True)
    maven = Path(os.environ["ELMOS_MAVEN_EXECUTABLE"])
    java11 = Path(os.environ["ELMOS_JAVA_11_HOME"]); java21 = Path(os.environ["ELMOS_JAVA_21_HOME"])
    version = run([str(maven), "-version"], repo, java21, 120).stdout.splitlines()[0]
    if MAVEN_VERSION not in version: raise Failure("EXACT_MAVEN_VERSION_REQUIRED")
    source = workspace / "source"; target = workspace / "target"; logs = workspace / "logs"; logs.mkdir(parents=True)
    materialize_source(source, route)
    source_build = run([str(maven), "-B", "--no-transfer-progress", "clean", "verify", "package"], source, java11)
    fcm = extract_fcm(source, route)
    materialize_target(target, route, fcm)
    target_build = run([str(maven), "-B", "--no-transfer-progress", "clean", "verify", "package"], target, java21)
    source_runtime = source_mvc_runtime(source, logs / "source.log") if route.family == "spring-mvc" else source_core_runtime(source)
    target_observed = target_runtime(target, route, java21, logs / "target.log")
    source_values = source_runtime["responses"] if route.family == "spring-mvc" else source_runtime["results"]
    target_values = target_observed["responses"] if route.family == "spring-mvc" else target_observed["results"]
    if source_values != target_values: raise Failure(f"FCM_BEHAVIOR_DIFFERENCE:{source_values!r}:{target_values!r}")
    evidence = {"schema_version": 1, "route_id": route.route_id, "execution_status": "PASSED_LOCAL", "recorded_tuple": {"source_boot": route.source_spring, "source_java": "11", "target_boot": route.target_boot, "target_java": "21"}, "build_tool": "maven", "source_family": route.family, "source": {"spring_framework": route.source_spring, "build": "PASSED", "build_tail": source_build.stdout[-2000:], "runtime": source_runtime}, "target": {"boot": route.target_boot, "build": "PASSED", "build_tail": target_build.stdout[-2000:], "runtime": target_observed}, "transformation": {"engine": "ELMOS_FCM_TARGET_GENERATOR", "fcm": fcm, "fcm_sha256": sha256(target / ".elmos/framework-contract-model.json"), "generator_sha256": sha256(Path(__file__)), "source_tree": {str(path.relative_to(source)): sha256(path) for path in sorted(source.rglob("*")) if path.is_file() and "target" not in path.parts}}, "behavioral_parity": True, "probe_ids": list(PROBE_IDS), "authorized_customer_repository": "NOT_RUN", "rootless_runner": "NOT_RUN", "independent_verification": "NOT_RUN", "external_evidence_status": "NOT_RUN", "certification_status": "NOT_CERTIFIED"}
    destination = repo / "evidence/spring-routes" / f"{route.route_id}.json"
    temporary = destination.with_suffix(".json.tmp"); temporary.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"); os.replace(temporary, destination)
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--route", required=True, choices=sorted(ROUTES)); parser.add_argument("--repo-root", default="."); parser.add_argument("--workspace")
    args = parser.parse_args(); repo = Path(args.repo_root).resolve(); route = ROUTES[args.route]
    try:
        if args.workspace: evidence = execute(repo, Path(args.workspace).resolve(), route)
        else:
            with tempfile.TemporaryDirectory(prefix="elmos-nonboot-fcm.") as temporary: evidence = execute(repo, Path(temporary), route)
    except (Failure, KeyError, StopIteration) as exc:
        print(f"FAIL:{route.route_id}:{exc}"); return 1
    print(f"PASS:{route.route_id}:{evidence['recorded_tuple']}"); return 0


if __name__ == "__main__": raise SystemExit(main())
