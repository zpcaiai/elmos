from __future__ import annotations

import json
from html import escape

from .container_images import MAVEN_IMAGE, TEMURIN_JRE_IMAGE
from .java_production_target import render_java_production
from .models import FieldSpec, SynthesisRequest, pascal
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
    if request.requires_database or request.requires_authentication:
        return render_java_production(request, port)
    package_path = request.namespace.replace(".", "/")
    app_class = f"{request.project_class}Application"
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
              <description>{escape(request.description)}</description>
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
        "openapi.yaml": openapi_yaml(request, server_port=port),
        "Dockerfile": clean(
            f"""
            FROM {MAVEN_IMAGE} AS build
            WORKDIR /workspace
            COPY pom.xml ./
            RUN mvn -B -DskipTests dependency:go-offline
            COPY src ./src
            RUN mvn -B package

            FROM {TEMURIN_JRE_IMAGE}
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
                  - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
                  - uses: actions/setup-java@c1e323688fd81a25caa38c78aa6df2d33d3e20d9 # v4
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
    for entity in request.entities:
        entity_class = pascal(entity.singular)
        request_class = f"Upsert{entity_class}Request"
        record_fields = ",\n        ".join(_field_declaration(field) for field in entity.fields)
        entity_fields = ",\n        ".join(
            ["String id", *(f"{_java_type(field)} {camel(field.name)}" for field in entity.fields)]
        )
        request_args = ", ".join(f"request.{camel(field.name)}()" for field in entity.fields)
        sample = json.dumps(sample_payload(request, entity), separators=(",", ":"))
        java_sample = sample.replace("\\", "\\\\").replace('"', '\\"')
        files.update(
            {
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
                            return records.values().stream()
                                    .sorted(Comparator.comparing({entity_class}::id))
                                    .toList();
                        }}

                        public Optional<{entity_class}> findById(String id) {{
                            return Optional.ofNullable(records.get(id));
                        }}

                        public {entity_class} create({request_class} request) {{
                            var value = new {entity_class}(UUID.randomUUID().toString(), {request_args});
                            records.put(value.id(), value);
                            return value;
                        }}

                        public Optional<{entity_class}> update(String id, {request_class} request) {{
                            if (!records.containsKey(id)) {{
                                return Optional.empty();
                            }}
                            var value = new {entity_class}(id, {request_args});
                            records.put(id, value);
                            return Optional.of(value);
                        }}

                        public boolean delete(String id) {{
                            return records.remove(id) != null;
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
                    @RequestMapping("/api/v1/{entity.plural}")
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
                        public ResponseEntity<{entity_class}> create(
                                @Valid @RequestBody {request_class} request) {{
                            var created = repository.create(request);
                            return ResponseEntity
                                    .created(URI.create("/api/v1/{entity.plural}/" + created.id()))
                                    .body(created);
                        }}

                        @PutMapping("/{{id}}")
                        public ResponseEntity<{entity_class}> update(
                                @PathVariable String id,
                                @Valid @RequestBody {request_class} request) {{
                            return repository.update(id, request)
                                    .map(ResponseEntity::ok)
                                    .orElseGet(() -> ResponseEntity.notFound().build());
                        }}

                        @DeleteMapping("/{{id}}")
                        public ResponseEntity<Void> delete(@PathVariable String id) {{
                            return repository.delete(id)
                                    ? ResponseEntity.noContent().build()
                                    : ResponseEntity.notFound().build();
                        }}
                    }}
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

                    import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
                    import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
                    import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
                    import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
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
                            var result = mvc.perform(post("/api/v1/{entity.plural}")
                                            .contentType(MediaType.APPLICATION_JSON)
                                            .content("{java_sample}"))
                                    .andExpect(status().isCreated())
                                    .andExpect(jsonPath("$.id").isNotEmpty())
                                    .andReturn();
                            var id = com.jayway.jsonpath.JsonPath
                                    .parse(result.getResponse().getContentAsString())
                                    .read("$.id", String.class);
                            mvc.perform(get("/api/v1/{entity.plural}/" + id))
                                    .andExpect(status().isOk());
                            mvc.perform(put("/api/v1/{entity.plural}/" + id)
                                            .contentType(MediaType.APPLICATION_JSON)
                                            .content("{java_sample}"))
                                    .andExpect(status().isOk());
                            mvc.perform(delete("/api/v1/{entity.plural}/" + id))
                                    .andExpect(status().isNoContent());
                            mvc.perform(get("/api/v1/{entity.plural}/" + id))
                                    .andExpect(status().isNotFound());
                        }}
                    }}
                    """
                ),
            }
        )
    return files
