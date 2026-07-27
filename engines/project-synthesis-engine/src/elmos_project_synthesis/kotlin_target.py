from __future__ import annotations

import json
from importlib.resources import files

from .container_images import GRADLE_IMAGE, TEMURIN_JRE_IMAGE
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


def _gradle_lock() -> str:
    lock = (
        files("elmos_project_synthesis")
        .joinpath("templates", "kotlin", "gradle.lockfile")
        .read_text(encoding="utf-8")
    )
    if "io.ktor:ktor-server-core:3.2.3=" not in lock or "empty=" not in lock:
        raise ValueError("KOTLIN_LOCK_TEMPLATE_INVALID")
    return lock


def _kotlin_type(field: FieldSpec) -> str:
    base = {
        "string": "String",
        "integer": "Long",
        "number": "Double",
        "boolean": "Boolean",
        "datetime": "String",
    }[field.type]
    return base if field.required else f"{base}?"


def render_kotlin(request: SynthesisRequest, port: int) -> dict[str, str]:
    model_blocks: list[str] = []
    store_blocks: list[str] = []
    route_blocks: list[str] = []
    test_blocks: list[str] = []
    for entity in request.entities:
        entity_class = pascal(entity.singular)
        upsert = f"{entity_class}Upsert"
        rendered_fields: list[str] = []
        for field in entity.fields:
            property_name = camel(field.name)
            annotation = f'@SerialName("{field.name}") ' if property_name != field.name else ""
            rendered_fields.append(
                f"{annotation}val {property_name}: {_kotlin_type(field)}" + (" = null" if not field.required else "")
            )
        fields = ",\n    ".join(rendered_fields)
        record_args = ", ".join(f"{camel(field.name)} = payload.{camel(field.name)}" for field in entity.fields)
        model_blocks.append(
            clean(
                f"""
                @Serializable
                data class {upsert}(
                    {fields}
                )

                @Serializable
                data class {entity_class}(
                    val id: String,
                    {fields}
                )
                """
            ).rstrip()
        )
        store_name = f"{camel(entity.plural)}Store"
        store_blocks.append(f"private val {store_name} = ConcurrentHashMap<String, {entity_class}>()")
        route_blocks.append(
            clean(
                f"""
                route("/api/v1/{entity.plural}") {{
                    get {{
                        call.respond({store_name}.values.sortedBy {{ it.id }})
                    }}
                    post {{
                        val payload = call.receive<{upsert}>()
                        val value = {entity_class}(id = UUID.randomUUID().toString(), {record_args})
                        {store_name}[value.id] = value
                        call.respond(HttpStatusCode.Created, value)
                    }}
                    get("{{id}}") {{
                        val value = {store_name}[call.parameters["id"]]
                            ?: return@get call.respond(HttpStatusCode.NotFound)
                        call.respond(value)
                    }}
                    put("{{id}}") {{
                        val id = call.parameters["id"] ?: return@put call.respond(HttpStatusCode.BadRequest)
                        if (!{store_name}.containsKey(id)) return@put call.respond(HttpStatusCode.NotFound)
                        val payload = call.receive<{upsert}>()
                        val value = {entity_class}(id = id, {record_args})
                        {store_name}[id] = value
                        call.respond(value)
                    }}
                    delete("{{id}}") {{
                        val id = call.parameters["id"] ?: return@delete call.respond(HttpStatusCode.BadRequest)
                        if ({store_name}.remove(id) == null) return@delete call.respond(HttpStatusCode.NotFound)
                        call.respond(HttpStatusCode.NoContent)
                    }}
                }}
                """
            ).rstrip()
        )
        sample = json.dumps(sample_payload(request, entity), ensure_ascii=False, separators=(",", ":"))
        escaped_sample = json.dumps(sample, ensure_ascii=False)
        test_blocks.append(
            clean(
                f"""
                val created{entity_class} = client.post("/api/v1/{entity.plural}") {{
                    setBody(TextContent({escaped_sample}, ContentType.Application.Json))
                }}
                assertEquals(HttpStatusCode.Created, created{entity_class}.status)
                val id{entity_class} = Json.parseToJsonElement(
                    created{entity_class}.bodyAsText()
                ).jsonObject["id"]!!.jsonPrimitive.content
                assertEquals(HttpStatusCode.OK, client.get("/api/v1/{entity.plural}/$id{entity_class}").status)
                assertEquals(HttpStatusCode.OK, client.put("/api/v1/{entity.plural}/$id{entity_class}") {{
                    setBody(TextContent({escaped_sample}, ContentType.Application.Json))
                }}.status)
                assertEquals(
                    HttpStatusCode.NoContent,
                    client.delete("/api/v1/{entity.plural}/$id{entity_class}").status,
                )
                assertEquals(HttpStatusCode.NotFound, client.get("/api/v1/{entity.plural}/$id{entity_class}").status)
                """
            ).rstrip()
        )
    models = "\n\n".join(model_blocks)
    stores = "\n".join(store_blocks)
    routes = "\n\n".join(route_blocks)
    tests = "\n\n".join(test_blocks)
    package_path = request.namespace.replace(".", "/")
    return {
        ".gitignore": gitignore(),
        ".dockerignore": dockerignore(),
        ".env.example": env_example(request, port),
        "settings.gradle.kts": clean(
            f"""
            rootProject.name = "{request.project_name}"
            """
        ),
        "build.gradle.kts": clean(
            f"""
            plugins {{
                kotlin("jvm") version "2.2.20"
                kotlin("plugin.serialization") version "2.2.20"
                application
            }}

            repositories {{
                mavenCentral()
            }}

            dependencies {{
                implementation("io.ktor:ktor-server-core:3.2.3")
                implementation("io.ktor:ktor-server-netty:3.2.3")
                implementation("io.ktor:ktor-server-content-negotiation:3.2.3")
                implementation("io.ktor:ktor-serialization-kotlinx-json:3.2.3")
                testImplementation("io.ktor:ktor-server-test-host:3.2.3")
                testImplementation(kotlin("test"))
            }}

            kotlin {{
                jvmToolchain(21)
            }}

            application {{
                mainClass.set("{request.namespace}.ApplicationKt")
            }}

            dependencyLocking {{
                lockAllConfigurations()
            }}

            tasks.test {{
                useJUnitPlatform()
            }}
            """
        ),
        "gradle.lockfile": _gradle_lock(),
        "gradle.properties": clean(
            """
            org.gradle.caching=true
            org.gradle.configuration-cache=true
            org.gradle.daemon=false
            kotlin.code.style=official
            """
        ),
        f"src/main/kotlin/{package_path}/Models.kt": clean(
            f"""
            package {request.namespace}

            import kotlinx.serialization.SerialName
            import kotlinx.serialization.Serializable

            {models}
            """
        ),
        f"src/main/kotlin/{package_path}/Application.kt": clean(
            f"""
            package {request.namespace}

            import io.ktor.http.HttpStatusCode
            import io.ktor.serialization.kotlinx.json.json
            import io.ktor.server.application.Application
            import io.ktor.server.application.call
            import io.ktor.server.application.install
            import io.ktor.server.engine.embeddedServer
            import io.ktor.server.netty.Netty
            import io.ktor.server.plugins.contentnegotiation.ContentNegotiation
            import io.ktor.server.request.receive
            import io.ktor.server.response.respond
            import io.ktor.server.routing.delete
            import io.ktor.server.routing.get
            import io.ktor.server.routing.post
            import io.ktor.server.routing.put
            import io.ktor.server.routing.route
            import io.ktor.server.routing.routing
            import java.util.UUID
            import java.util.concurrent.ConcurrentHashMap

            {stores}

            fun Application.module() {{
                install(ContentNegotiation) {{ json() }}
                routing {{
                    get("/health") {{
                        call.respond(mapOf("status" to "UP", "service" to "{request.project_name}"))
                    }}
                    {routes}
                }}
            }}

            fun main() {{
                val port = System.getenv("PORT")?.toIntOrNull() ?: {port}
                val host = System.getenv("HOST") ?: "127.0.0.1"
                embeddedServer(Netty, port = port, host = host, module = Application::module).start(wait = true)
            }}
            """
        ),
        f"src/test/kotlin/{package_path}/ApplicationTest.kt": clean(
            f"""
            package {request.namespace}

            import io.ktor.client.request.delete
            import io.ktor.client.request.get
            import io.ktor.client.request.post
            import io.ktor.client.request.put
            import io.ktor.client.request.setBody
            import io.ktor.client.statement.bodyAsText
            import io.ktor.http.ContentType
            import io.ktor.http.HttpStatusCode
            import io.ktor.http.content.TextContent
            import io.ktor.server.testing.testApplication
            import kotlinx.serialization.json.Json
            import kotlinx.serialization.json.jsonObject
            import kotlinx.serialization.json.jsonPrimitive
            import kotlin.test.Test
            import kotlin.test.assertEquals

            class ApplicationTest {{
                @Test
                fun fullCrudAndHealthJourney() = testApplication {{
                    application {{ module() }}
                    assertEquals(HttpStatusCode.OK, client.get("/health").status)
                    {tests}
                }}
            }}
            """
        ),
        "openapi.yaml": openapi_yaml(request, server_port=port),
        "Dockerfile": clean(
            f"""
            FROM {GRADLE_IMAGE} AS build
            WORKDIR /workspace
            COPY . .
            RUN gradle --no-daemon test installDist

            FROM {TEMURIN_JRE_IMAGE}
            ENV HOST=0.0.0.0
            RUN addgroup -S app && adduser -S -G app -u 10001 app
            WORKDIR /app
            COPY --from=build /workspace/build/install/{request.project_name} ./
            USER 10001:10001
            EXPOSE {port}
            ENTRYPOINT ["bin/{request.project_name}"]
            """
        ),
        "deploy/kubernetes.yaml": kubernetes_yaml(request, language="kotlin", port=port),
        ".github/workflows/ci.yml": clean(
            """
            name: kotlin-ci
            on: [push, pull_request]
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
                  - uses: gradle/actions/setup-gradle@ed408507eac070d1f99cc633dbcf757c94c7933a # v4
                    with:
                      gradle-version: 8.14.3
                  - run: gradle --no-daemon test build
            """
        ),
        "Makefile": clean(
            f"""
            .PHONY: update-lock test build run
            update-lock:
            \tgradle --no-daemon dependencies --write-locks
            test:
            \tgradle --no-daemon test
            build:
            \tgradle --no-daemon build
            run:
            \tPORT={port} gradle --no-daemon run
            """
        ),
        "README.md": target_readme(
            request,
            language="Kotlin 2.2.20 / JVM 21",
            framework="Ktor 3.2.3",
            port=port,
            commands=f"gradle --no-daemon test build\nPORT={port} gradle --no-daemon run",
        ),
    }
