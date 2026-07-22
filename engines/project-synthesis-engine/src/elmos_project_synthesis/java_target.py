from __future__ import annotations

import json

from .models import FieldSpec, SynthesisRequest
from .rendering import (
    camel,
    clean,
    dockerignore,
    env_example,
    gitignore,
    kubernetes_yaml,
    openapi_yaml,
    sample_payload,
    target_readme,
)


def _java_type(field: FieldSpec) -> str:
    return {
        "string": "String",
        "integer": "Long",
        "number": "Double",
        "boolean": "Boolean",
        "datetime": "java.time.Instant",
    }[field.type]


def _field_declaration(field: FieldSpec) -> str:
    annotations: list[str] = []
    if field.required and field.type == "string":
        annotations.append("@jakarta.validation.constraints.NotBlank")
    elif field.required:
        annotations.append("@jakarta.validation.constraints.NotNull")
    prefix = " ".join(annotations)
    if prefix:
        prefix += " "
    return f"{prefix}{_java_type(field)} {camel(field.name)}"


def render_java(request: SynthesisRequest, port: int) -> dict[str, str]:
    package_path = request.namespace.replace(".", "/")
    app_class = f"{request.project_class}Application"
    entity_class = request.entity_class
    request_class = f"Create{entity_class}Request"
    record_fields = ",\n        ".join(_field_declaration(field) for field in request.entity.fields)
    entity_fields = ",\n        ".join(
        ["String id", *(f"{_java_type(field)} {camel(field.name)}" for field in request.entity.fields)]
    )
    request_args = ", ".join(f"request.{camel(field.name)}()" for field in request.entity.fields)
    sample = json.dumps(sample_payload(request), separators=(",", ":"))
    java_sample = sample.replace("\\", "\\\\").replace('"', '\\"')
    app_slug = request.project_name
    files: dict[str, str] = {
        ".gitignore": gitignore(),
        ".dockerignore": dockerignore(),
        ".env.example": env_example(request, port),
        "pom.xml": clean(
            f"""
            <?xml version="1.0" encoding="UTF-8"?>
            <project xmlns="http://maven.apache.org/POM/4.0.0"
                     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                     xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
              <modelVersion>4.0.0</modelVersion>
              <parent>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-starter-parent</artifactId>
                <version>3.5.3</version>
                <relativePath/>
              </parent>
              <groupId>{request.namespace}</groupId>
              <artifactId>{app_slug}</artifactId>
              <version>1.0.0-SNAPSHOT</version>
              <name>{app_slug}</name>
              <description>{request.description}</description>
              <properties>
                <java.version>21</java.version>
              </properties>
              <dependencies>
                <dependency>
                  <groupId>org.springframework.boot</groupId>
                  <artifactId>spring-boot-starter-web</artifactId>
                </dependency>
                <dependency>
                  <groupId>org.springframework.boot</groupId>
                  <artifactId>spring-boot-starter-validation</artifactId>
                </dependency>
                <dependency>
                  <groupId>org.springframework.boot</groupId>
                  <artifactId>spring-boot-starter-actuator</artifactId>
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
        ),
        f"src/main/java/{package_path}/{app_class}.java": clean(
            f"""
            package {request.namespace};

            import org.springframework.boot.SpringApplication;
            import org.springframework.boot.autoconfigure.SpringBootApplication;

            @SpringBootApplication
            public class {app_class} {{
                public static void main(String[] args) {{
                    SpringApplication.run({app_class}.class, args);
                }}
            }}
            """
        ),
        f"src/main/java/{package_path}/api/{entity_class}.java": clean(
            f"""
            package {request.namespace}.api;

            public record {entity_class}(
                    {entity_fields}
            ) {{}}
            """
        ),
        f"src/main/java/{package_path}/api/{request_class}.java": clean(
            f"""
            package {request.namespace}.api;

            public record {request_class}(
                    {record_fields}
            ) {{}}
            """
        ),
        f"src/main/java/{package_path}/api/{entity_class}Repository.java": clean(
            f"""
            package {request.namespace}.api;

            import org.springframework.stereotype.Repository;

            import java.util.Comparator;
            import java.util.List;
            import java.util.Optional;
            import java.util.UUID;
            import java.util.concurrent.ConcurrentHashMap;

            @Repository
            public class {entity_class}Repository {{
                private final ConcurrentHashMap<String, {entity_class}> records = new ConcurrentHashMap<>();

                public List<{entity_class}> findAll() {{
                    return records.values().stream().sorted(Comparator.comparing({entity_class}::id)).toList();
                }}

                public Optional<{entity_class}> findById(String id) {{
                    return Optional.ofNullable(records.get(id));
                }}

                public {entity_class} create({request_class} request) {{
                    var value = new {entity_class}(UUID.randomUUID().toString(), {request_args});
                    records.put(value.id(), value);
                    return value;
                }}
            }}
            """
        ),
        f"src/main/java/{package_path}/api/{entity_class}Controller.java": clean(
            f"""
            package {request.namespace}.api;

            import jakarta.validation.Valid;
            import org.springframework.http.ResponseEntity;
            import org.springframework.web.bind.annotation.*;

            import java.net.URI;
            import java.util.List;

            @RestController
            @RequestMapping("/api/v1/{request.entity.plural}")
            public class {entity_class}Controller {{
                private final {entity_class}Repository repository;

                public {entity_class}Controller({entity_class}Repository repository) {{
                    this.repository = repository;
                }}

                @GetMapping
                public List<{entity_class}> list() {{
                    return repository.findAll();
                }}

                @GetMapping("/{{id}}")
                public ResponseEntity<{entity_class}> get(@PathVariable String id) {{
                    return repository.findById(id)
                            .map(ResponseEntity::ok)
                            .orElseGet(() -> ResponseEntity.notFound().build());
                }}

                @PostMapping
                public ResponseEntity<{entity_class}> create(@Valid @RequestBody {request_class} request) {{
                    var created = repository.create(request);
                    return ResponseEntity
                            .created(URI.create("/api/v1/{request.entity.plural}/" + created.id()))
                            .body(created);
                }}
            }}
            """
        ),
        f"src/main/java/{package_path}/api/HealthController.java": clean(
            f"""
            package {request.namespace}.api;

            import org.springframework.web.bind.annotation.GetMapping;
            import org.springframework.web.bind.annotation.RestController;

            import java.util.Map;

            @RestController
            public class HealthController {{
                @GetMapping("/health")
                public Map<String, String> health() {{
                    return Map.of("status", "UP", "service", "{request.project_name}");
                }}
            }}
            """
        ),
        "src/main/resources/application.yml": clean(
            f"""
            spring:
              application:
                name: ${{APP_NAME:{request.project_name}}}
            server:
              port: ${{PORT:{port}}}
              shutdown: graceful
            management:
              endpoints:
                web:
                  exposure:
                    include: health,info
            logging:
              level:
                root: ${{LOG_LEVEL:INFO}}
            """
        ),
        f"src/test/java/{package_path}/api/{entity_class}ApiTest.java": clean(
            f"""
            package {request.namespace}.api;

            import org.junit.jupiter.api.Test;
            import org.springframework.beans.factory.annotation.Autowired;
            import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
            import org.springframework.boot.test.context.SpringBootTest;
            import org.springframework.http.MediaType;
            import org.springframework.test.web.servlet.MockMvc;

            import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
            import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
            import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
            import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

            @SpringBootTest
            @AutoConfigureMockMvc
            class {entity_class}ApiTest {{
                @Autowired MockMvc mvc;

                @Test
                void requirementTracedCrudAndHealthJourney() throws Exception {{
                    mvc.perform(get("/health"))
                            .andExpect(status().isOk())
                            .andExpect(jsonPath("$.status").value("UP"));
                    mvc.perform(post("/api/v1/{request.entity.plural}")
                                    .contentType(MediaType.APPLICATION_JSON)
                                    .content("{java_sample}"))
                            .andExpect(status().isCreated())
                            .andExpect(jsonPath("$.id").isNotEmpty());
                    mvc.perform(get("/api/v1/{request.entity.plural}"))
                            .andExpect(status().isOk())
                            .andExpect(jsonPath("$[0].id").isNotEmpty());
                }}
            }}
            """
        ),
        "openapi.yaml": openapi_yaml(request, server_port=port),
        "Dockerfile": clean(
            f"""
            FROM maven:3.9.10-eclipse-temurin-21 AS build
            WORKDIR /workspace
            COPY pom.xml ./
            RUN mvn -B -DskipTests dependency:go-offline
            COPY src ./src
            RUN mvn -B package

            FROM eclipse-temurin:21.0.7_6-jre-alpine
            RUN addgroup -S app && adduser -S -G app -u 10001 app
            WORKDIR /app
            COPY --from=build /workspace/target/*.jar app.jar
            USER 10001:10001
            EXPOSE {port}
            ENTRYPOINT ["java", "-jar", "/app/app.jar"]
            """
        ),
        "deploy/kubernetes.yaml": kubernetes_yaml(request, language="java", port=port),
        ".github/workflows/ci.yml": clean(
            """
            name: java-ci
            on:
              push:
              pull_request:
            permissions:
              contents: read
            jobs:
              test:
                runs-on: ubuntu-latest
                steps:
                  - uses: actions/checkout@v4
                  - uses: actions/setup-java@v4
                    with:
                      distribution: temurin
                      java-version: '21'
                      cache: maven
                  - run: mvn -B verify
            """
        ),
        "Makefile": clean(
            """
            .PHONY: test run package
            test:
            \tmvn -B test
            run:
            \tmvn spring-boot:run
            package:
            \tmvn -B package
            """
        ),
        "README.md": target_readme(
            request,
            language="Java 21",
            framework="Spring Boot 3.5.3",
            port=port,
            commands=f"mvn -B test\nPORT={port} mvn spring-boot:run",
        ),
    }
    return files
