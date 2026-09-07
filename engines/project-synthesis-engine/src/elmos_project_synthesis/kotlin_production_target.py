# ruff: noqa: E501
"""Ktor production profile: PostgreSQL, forced RLS, JWT or OIDC bearer.

Same shared contract and harness as the Python, Java, Go, TypeScript and C#
profiles. Verification uses java-jwt so both HS256 and RS256 are handled by one
library, and the store speaks plain JDBC so the tenant binding stays visible
rather than hidden behind an ORM session.
"""
from __future__ import annotations

import json
from importlib.resources import files

from .container_images import GRADLE_IMAGE, TEMURIN_JRE_IMAGE
from .models import FieldSpec, SynthesisRequest, pascal
from .production_contract import (
    ENV_AUTH_AUDIENCE,
    ENV_AUTH_ISSUER,
    ENV_DATABASE_URL_FILE,
    ENV_JWT_SECRET_FILE,
    ENV_OIDC_JWKS_FILE,
    ENV_OIDC_PRIVATE_KEY_FILE,
    TENANT_CLAIM,
    TENANT_SETTING,
    all_entity_sql,
    production_contract,
)
from .production_runtime import render_local_runtime
from .rendering import (
    camel,
    clean,
    dockerignore,
    env_example,
    gitignore,
    kubernetes_yaml,
    openapi_yaml,
    pretty_json,
    target_readme,
)

KTOR_VERSION = "3.2.3"
KOTLIN_VERSION = "2.2.20"
JAVA_JWT_VERSION = "4.5.0"
POSTGRES_JDBC_VERSION = "42.7.7"


def _production_lock() -> str:
    """Read the pinned dependency lock for the production dependency set.

    The template is generated with ``gradle --write-locks`` against Maven
    Central and committed, exactly like the starter profile's lock. Until it
    exists this emitter cannot produce a reproducible workspace, so it fails
    with a named reason rather than emitting an unlocked build.
    """
    template = files("elmos_project_synthesis").joinpath(
        "templates", "kotlin", "gradle.production.lockfile"
    )
    try:
        lock = template.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as error:
        raise ValueError("KOTLIN_PRODUCTION_LOCK_TEMPLATE_MISSING") from error
    for marker in (
        f"io.ktor:ktor-server-core:{KTOR_VERSION}=",
        f"org.postgresql:postgresql:{POSTGRES_JDBC_VERSION}=",
        f"com.auth0:java-jwt:{JAVA_JWT_VERSION}=",
        "empty=",
    ):
        if marker not in lock:
            raise ValueError(f"KOTLIN_PRODUCTION_LOCK_TEMPLATE_INVALID:{marker}")
    return lock


def _kotlin_type(field: FieldSpec) -> str:
    return {
        "string": "String",
        "integer": "Long",
        "number": "Double",
        "boolean": "Boolean",
        "datetime": "String",
    }[field.type]


def _reader(field: FieldSpec, index: int) -> str:
    return {
        "string": f"rows.getString({index})",
        "integer": f"rows.getLong({index})",
        "number": f"rows.getBigDecimal({index}).toDouble()",
        "boolean": f"rows.getBoolean({index})",
        "datetime": f"rows.getString({index})",
    }[field.type]


def _sample_json(field: FieldSpec) -> object:
    return {
        "string": f"sample-{field.name}",
        "integer": 1,
        "number": 1.5,
        "boolean": True,
        "datetime": "2026-01-01T00:00:00Z",
    }[field.type]


def _security_source(request: SynthesisRequest) -> str:
    # A Kotlin class body accepts declarations, not statements, so the key
    # material is assembled in a top-level function the class then calls from
    # its property initializer.
    if request.auth_mode == "jwt":
        algorithm = f"""
        val secret = java.io.File(requiredEnvironment("{ENV_JWT_SECRET_FILE}")).readText().trim()
        require(secret.length >= 32) {{ "JWT_SECRET_TOO_SHORT" }}
        return Algorithm.HMAC256(secret)
        """
    else:
        algorithm = f"""
        val jwks = Json.parseToJsonElement(
            java.io.File(requiredEnvironment("{ENV_OIDC_JWKS_FILE}")).readText(),
        ).jsonObject
        val keys = jwks["keys"]!!.jsonArray
        require(keys.size == 1) {{ "OIDC_JWKS_MUST_CONTAIN_EXACTLY_ONE_KEY" }}
        val key = keys[0].jsonObject
        val modulus = java.math.BigInteger(
            1,
            java.util.Base64.getUrlDecoder().decode(key["n"]!!.jsonPrimitive.content),
        )
        val exponent = java.math.BigInteger(
            1,
            java.util.Base64.getUrlDecoder().decode(key["e"]!!.jsonPrimitive.content),
        )
        val publicKey = java.security.KeyFactory.getInstance("RSA").generatePublic(
            java.security.spec.RSAPublicKeySpec(modulus, exponent),
        ) as java.security.interfaces.RSAPublicKey
        return Algorithm.RSA256(publicKey, null)
        """
    algorithm = clean(algorithm).rstrip().replace("\n", "\n    ")
    return clean(
        f"""
        package {request.namespace}

        import com.auth0.jwt.JWT
        import com.auth0.jwt.algorithms.Algorithm
        import com.auth0.jwt.exceptions.JWTVerificationException
        import kotlinx.serialization.json.Json
        import kotlinx.serialization.json.jsonArray
        import kotlinx.serialization.json.jsonObject
        import kotlinx.serialization.json.jsonPrimitive

        fun requiredEnvironment(name: String): String =
            System.getenv(name)?.takeIf {{ it.isNotBlank() }}
                ?: throw IllegalStateException("REQUIRED_ENVIRONMENT_MISSING:$name")

        private fun buildAlgorithm(): Algorithm {{
            {algorithm}
        }}

        /**
         * Bearer verification for the production profile.
         *
         * A structurally valid signature is not authorization: issuer,
         * audience, expiry and the tenant claim the database policy is keyed on
         * are all mandatory, so a token minted for another service or another
         * tenant is refused here rather than becoming a cross-tenant read.
         */
        class TenantAuthenticator {{
            private val algorithm: Algorithm = buildAlgorithm()

            private val verifier = JWT.require(algorithm)
                .withIssuer(requiredEnvironment("{ENV_AUTH_ISSUER}"))
                .withAudience(requiredEnvironment("{ENV_AUTH_AUDIENCE}"))
                .acceptLeeway(0)
                .build()

            fun tenantFrom(authorization: String?): String? {{
                val token = authorization?.removePrefix("Bearer ")?.takeIf {{ it != authorization }} ?: return null
                return try {{
                    val decoded = verifier.verify(token)
                    if (decoded.expiresAt == null) return null
                    decoded.getClaim("{TENANT_CLAIM}").asString()?.takeIf {{ it.isNotBlank() }}
                }} catch (error: JWTVerificationException) {{
                    null
                }}
            }}
        }}
        """
    )


def _store_source(request: SynthesisRequest) -> str:
    statements = {item.entity: item for item in all_entity_sql(request, placeholder="?")}
    classes: list[str] = []
    for entity in request.entities:
        entity_class = pascal(entity.singular)
        sql = statements[entity.singular]
        upsert_sql = sql.upsert_sql
        properties = ",\n    ".join(
            f"val {camel(field.name)}: {_kotlin_type(field)}" for field in entity.fields
        )
        read_values = ",\n                    ".join(
            ["rows.getString(1)"]
            + [_reader(field, index + 2) for index, field in enumerate(entity.fields)]
        )
        bind_upsert = "\n                statement.".join(
            f"setObject({index + 3}, payload.{camel(field.name)})"
            for index, field in enumerate(entity.fields)
        )
        classes.append(
            f"""
            @Serializable
            data class {entity_class}Upsert(
                {properties}
            )

            @Serializable
            data class {entity_class}(
                val id: String,
                {properties}
            )

            /**
             * Every statement runs inside one tenant-scoped transaction.
             *
             * {TENANT_SETTING} is applied with set_config(..., true) so it is
             * transaction local and cannot leak to the next borrower of a pooled
             * connection. Row level security is FORCED on every table, so that
             * binding -- not the SQL text -- confines a request to its tenant.
             */
            class {entity_class}Store(private val jdbcUrl: String, private val user: String, private val password: String) {{

                private fun <T> inTenant(tenantId: String, work: (Connection) -> T): T {{
                    require(tenantId.isNotBlank()) {{ "TENANT_ID_REQUIRED" }}
                    DriverManager.getConnection(jdbcUrl, user, password).use {{ connection ->
                        connection.autoCommit = false
                        try {{
                            connection.prepareStatement("SELECT set_config('{TENANT_SETTING}', ?, true)").use {{ bind ->
                                bind.setString(1, tenantId)
                                bind.execute()
                            }}
                            val result = work(connection)
                            connection.commit()
                            return result
                        }} catch (error: Exception) {{
                            connection.rollback()
                            throw error
                        }}
                    }}
                }}

                fun list(tenantId: String): List<{entity_class}> = inTenant(tenantId) {{ connection ->
                    val results = mutableListOf<{entity_class}>()
                    connection.prepareStatement({json.dumps(sql.list_sql)}).use {{ statement ->
                        statement.executeQuery().use {{ rows ->
                            while (rows.next()) {{
                                results.add(
                                    {entity_class}(
                                        {read_values}
                                    ),
                                )
                            }}
                        }}
                    }}
                    results
                }}

                fun find(tenantId: String, recordId: UUID): {entity_class}? = inTenant(tenantId) {{ connection ->
                    connection.prepareStatement({json.dumps(sql.get_sql)}).use {{ statement ->
                        statement.setObject(1, recordId)
                        statement.executeQuery().use {{ rows ->
                            if (!rows.next()) {{
                                null
                            }} else {{
                                {entity_class}(
                                    {read_values}
                                )
                            }}
                        }}
                    }}
                }}

                fun save(tenantId: String, recordId: UUID, payload: {entity_class}Upsert): {entity_class} =
                    inTenant(tenantId) {{ connection ->
                        connection.prepareStatement({json.dumps(upsert_sql)}).use {{ statement ->
                            statement.setString(1, tenantId)
                            statement.setObject(2, recordId)
                            statement.{bind_upsert}
                            statement.executeQuery().use {{ rows ->
                                check(rows.next()) {{ "UPSERT_RETURNED_NO_ROW" }}
                                {entity_class}(
                                    {read_values}
                                )
                            }}
                        }}
                    }}

                fun delete(tenantId: String, recordId: UUID): Boolean = inTenant(tenantId) {{ connection ->
                    connection.prepareStatement({json.dumps(sql.delete_sql)}).use {{ statement ->
                        statement.setObject(1, recordId)
                        statement.executeUpdate() > 0
                    }}
                }}
            }}
            """
        )
    joined = "\n".join(classes)
    return clean(
        f"""
        package {request.namespace}

        import kotlinx.serialization.Serializable
        import java.sql.Connection
        import java.sql.DriverManager
        import java.util.UUID

        {joined}
        """
    )


def _application_source(request: SynthesisRequest, port: int) -> str:
    store_vals = "\n            ".join(
        f"val {camel(entity.singular)}Store = {pascal(entity.singular)}Store(jdbc, user, password)"
        for entity in request.entities
    )
    route_blocks: list[str] = []
    for entity in request.entities:
        entity_class = pascal(entity.singular)
        store_name = f"{camel(entity.singular)}Store"
        required_checks = "\n                    ".join(
            f'if (payload.{camel(field.name)}.isBlank()) return@put call.respond(HttpStatusCode.UnprocessableEntity, mapOf("error" to "PAYLOAD_INVALID"))'
            for field in entity.fields
            if field.required and field.type == "string"
        ) or "// no blank-string constraints declared"
        route_blocks.append(
            f"""
                get("/{entity.plural}") {{
                    val tenant = requireTenant(authenticator) ?: return@get
                    call.respond({store_name}.list(tenant))
                }}
                get("/{entity.plural}/{{id}}") {{
                    val tenant = requireTenant(authenticator) ?: return@get
                    val recordId = requireRecordId() ?: return@get
                    val record = {store_name}.find(tenant, recordId)
                    if (record == null) {{
                        call.respond(HttpStatusCode.NotFound, mapOf("error" to "not_found"))
                    }} else {{
                        call.respond(record)
                    }}
                }}
                put("/{entity.plural}/{{id}}") {{
                    val tenant = requireTenant(authenticator) ?: return@put
                    val recordId = requireRecordId() ?: return@put
                    val payload = call.receive<{entity_class}Upsert>()
                    {required_checks}
                    call.respond({store_name}.save(tenant, recordId, payload))
                }}
                delete("/{entity.plural}/{{id}}") {{
                    val tenant = requireTenant(authenticator) ?: return@delete
                    val recordId = requireRecordId() ?: return@delete
                    {store_name}.delete(tenant, recordId)
                    call.respond(HttpStatusCode.NoContent)
                }}
            """
        )
    routes = "\n".join(route_blocks)
    return clean(
        f"""
        package {request.namespace}

        import io.ktor.http.HttpStatusCode
        import io.ktor.serialization.kotlinx.json.json
        import io.ktor.server.application.Application
        import io.ktor.server.application.install
        import io.ktor.server.engine.embeddedServer
        import io.ktor.server.netty.Netty
        import io.ktor.server.plugins.contentnegotiation.ContentNegotiation
        import io.ktor.server.request.receive
        import io.ktor.server.response.respond
        import io.ktor.server.routing.delete
        import io.ktor.server.routing.get
        import io.ktor.server.routing.put
        import io.ktor.server.routing.routing
        import io.ktor.server.routing.RoutingContext
        import java.net.URI
        import java.util.UUID

        private val UUID_PATTERN =
            Regex("^[0-9a-fA-F]{{8}}-[0-9a-fA-F]{{4}}-[0-9a-fA-F]{{4}}-[0-9a-fA-F]{{4}}-[0-9a-fA-F]{{12}}$")

        fun jdbcParts(): Triple<String, String, String> {{
            val url = java.io.File(requiredEnvironment("{ENV_DATABASE_URL_FILE}")).readText().trim()
            check(url.startsWith("postgresql://")) {{ "DATABASE_URL_SCHEME_UNSUPPORTED" }}
            val parsed = URI(url)
            val credentials = (parsed.userInfo ?: "").split(":", limit = 2)
            val port = if (parsed.port < 0) 5432 else parsed.port
            val database = parsed.path.removePrefix("/")
            return Triple(
                "jdbc:postgresql://${{parsed.host}}:$port/$database",
                credentials.getOrElse(0) {{ "" }},
                credentials.getOrElse(1) {{ "" }},
            )
        }}

        fun Application.module(
            authenticator: TenantAuthenticator = TenantAuthenticator(),
        ) {{
            val (jdbc, user, password) = jdbcParts()
            {store_vals}
            install(ContentNegotiation) {{ json() }}
            routing {{
                get("/health") {{
                    call.respond(mapOf("status" to "UP", "service" to "{request.project_name}"))
                }}
                {routes}
            }}
        }}

        private suspend fun RoutingContext.requireTenant(
            authenticator: TenantAuthenticator,
        ): String? {{
            val tenant = authenticator.tenantFrom(call.request.headers["Authorization"])
            if (tenant == null) {{
                call.respond(HttpStatusCode.Unauthorized, mapOf("error" to "unauthorized"))
            }}
            return tenant
        }}

        private suspend fun RoutingContext.requireRecordId(): UUID? {{
            val raw = call.parameters["id"] ?: ""
            if (!UUID_PATTERN.matches(raw)) {{
                call.respond(HttpStatusCode.UnprocessableEntity, mapOf("error" to "RECORD_ID_MUST_BE_UUID"))
                return null
            }}
            return UUID.fromString(raw)
        }}

        fun main() {{
            val port = System.getenv("PORT")?.toIntOrNull() ?: {port}
            val host = System.getenv("HOST") ?: "0.0.0.0"
            embeddedServer(Netty, port = port, host = host) {{ module() }}.start(wait = true)
        }}
        """
    )

def _integration_test_source(request: SynthesisRequest, port: int) -> str:
    entity = request.entities[0]
    body_json = json.dumps({field.name: _sample_json(field) for field in entity.fields})
    kotlin_body = body_json.replace("\\", "\\\\").replace('"', '\\"')
    if request.auth_mode == "jwt":
        signer = f"""
        private fun algorithm(valid: Boolean): Algorithm {{
            val secret = if (valid) {{
                java.io.File(System.getenv("{ENV_JWT_SECRET_FILE}")).readText().trim()
            }} else {{
                "an-entirely-different-secret-value-of-length"
            }}
            return Algorithm.HMAC256(secret)
        }}
        """
    else:
        signer = f"""
        private fun algorithm(valid: Boolean): Algorithm {{
            if (!valid) {{
                val generated = java.security.KeyPairGenerator.getInstance("RSA")
                generated.initialize(2048)
                val pair = generated.generateKeyPair()
                return Algorithm.RSA256(
                    pair.public as java.security.interfaces.RSAPublicKey,
                    pair.private as java.security.interfaces.RSAPrivateKey,
                )
            }}
            val pem = java.io.File(System.getenv("{ENV_OIDC_PRIVATE_KEY_FILE}")).readText()
                .replace("-----BEGIN PRIVATE KEY-----", "")
                .replace("-----END PRIVATE KEY-----", "")
                .replace(Regex("\\\\s"), "")
            val key = java.security.KeyFactory.getInstance("RSA").generatePrivate(
                java.security.spec.PKCS8EncodedKeySpec(java.util.Base64.getDecoder().decode(pem)),
            ) as java.security.interfaces.RSAPrivateKey
            return Algorithm.RSA256(null, key)
        }}
        """
    signer = clean(signer).rstrip().replace("\n", "\n    ")
    return clean(
        f"""
        package {request.namespace}

        import com.auth0.jwt.JWT
        import com.auth0.jwt.algorithms.Algorithm
        import java.net.URI
        import java.net.http.HttpClient
        import java.net.http.HttpRequest
        import java.net.http.HttpResponse
        import java.util.Date
        import java.util.UUID
        import kotlin.test.Test
        import kotlin.test.assertEquals
        import kotlin.test.assertFalse
        import kotlin.test.assertTrue
        import org.junit.jupiter.api.Tag

        /**
         * The ten-step scenario from production-contract.json, executed against
         * the PostgreSQL instance the runtime harness provisioned.
         */
        @Tag("integration")
        class ProductionIntegrationTest {{
            {signer}

            private fun token(tenant: String?, issuer: String, audience: String, valid: Boolean): String {{
                val builder = JWT.create()
                    .withIssuer(issuer)
                    .withAudience(audience)
                    .withSubject("integration-subject")
                    .withIssuedAt(Date())
                    .withExpiresAt(Date(System.currentTimeMillis() + 300_000))
                if (tenant != null) {{
                    builder.withClaim("{TENANT_CLAIM}", tenant)
                }}
                return builder.sign(algorithm(valid))
            }}

            private val client: HttpClient = HttpClient.newHttpClient()
            private val base = "http://127.0.0.1:" + (System.getenv("PORT") ?: "{port}")

            private fun send(method: String, path: String, bearer: String?, body: String?): HttpResponse<String> {{
                val builder = HttpRequest.newBuilder(URI.create(base + path))
                if (bearer != null) builder.header("Authorization", "Bearer $bearer")
                if (body == null) {{
                    builder.method(method, HttpRequest.BodyPublishers.noBody())
                }} else {{
                    builder.header("Content-Type", "application/json")
                        .method(method, HttpRequest.BodyPublishers.ofString(body))
                }}
                return client.send(builder.build(), HttpResponse.BodyHandlers.ofString())
            }}

            @Test
            fun runsTheSharedProductionScenario() {{
                val issuer = requireNotNull(System.getenv("{ENV_AUTH_ISSUER}"))
                val audience = requireNotNull(System.getenv("{ENV_AUTH_AUDIENCE}"))
                val tenantA = token("tenant-a", issuer, audience, true)
                val tenantB = token("tenant-b", issuer, audience, true)

                // health-unauthenticated
                assertEquals(200, send("GET", "/health", null, null).statusCode())
                // missing-token-rejected
                assertEquals(401, send("GET", "/{entity.plural}", null, null).statusCode())
                // bad-signature-rejected
                assertEquals(401, send("GET", "/{entity.plural}", token("tenant-a", issuer, audience, false), null).statusCode())
                // wrong-audience-rejected
                assertEquals(401, send("GET", "/{entity.plural}", token("tenant-a", issuer, "another-service", true), null).statusCode())
                // wrong-issuer-rejected
                assertEquals(401, send("GET", "/{entity.plural}", token("tenant-a", "https://attacker.invalid/", audience, true), null).statusCode())
                // missing-tenant-claim-rejected
                assertEquals(401, send("GET", "/{entity.plural}", token(null, issuer, audience, true), null).statusCode())

                // upsert-and-read
                val recordId = UUID.randomUUID().toString()
                val created = send("PUT", "/{entity.plural}/$recordId", tenantA, "{kotlin_body}")
                assertEquals(200, created.statusCode(), created.body())
                val read = send("GET", "/{entity.plural}/$recordId", tenantA, null)
                assertEquals(200, read.statusCode())
                assertTrue(read.body().contains(recordId))

                // list-scoped-to-tenant
                val listed = send("GET", "/{entity.plural}", tenantA, null)
                assertEquals(200, listed.statusCode())
                assertTrue(listed.body().contains(recordId))

                // cross-tenant-read-blocked
                assertEquals(404, send("GET", "/{entity.plural}/$recordId", tenantB, null).statusCode())
                assertFalse(send("GET", "/{entity.plural}", tenantB, null).body().contains(recordId))

                // delete-removes-record
                assertEquals(204, send("DELETE", "/{entity.plural}/$recordId", tenantA, null).statusCode())
                assertEquals(404, send("GET", "/{entity.plural}/$recordId", tenantA, null).statusCode())
            }}
        }}
        """
    )


def render_kotlin_production(request: SynthesisRequest, port: int) -> dict[str, str]:
    package_path = request.namespace.replace(".", "/")
    return {
        ".gitignore": gitignore(),
        ".dockerignore": dockerignore(),
        ".env.example": env_example(request, port),
        "production-contract.json": pretty_json(production_contract(request)),
        "settings.gradle.kts": clean(
            f"""
            rootProject.name = "{request.project_name}"
            """
        ),
        "build.gradle.kts": clean(
            f"""
            plugins {{
                kotlin("jvm") version "{KOTLIN_VERSION}"
                kotlin("plugin.serialization") version "{KOTLIN_VERSION}"
                application
            }}

            val elmosMavenRepository = providers.gradleProperty("elmosMavenRepository").orNull
            repositories {{
                if (elmosMavenRepository == null) {{
                    mavenCentral()
                }} else {{
                    maven {{ url = uri(elmosMavenRepository) }}
                }}
            }}

            dependencies {{
                implementation("io.ktor:ktor-server-core:{KTOR_VERSION}")
                implementation("io.ktor:ktor-server-netty:{KTOR_VERSION}")
                implementation("io.ktor:ktor-server-content-negotiation:{KTOR_VERSION}")
                implementation("io.ktor:ktor-serialization-kotlinx-json:{KTOR_VERSION}")
                implementation("org.postgresql:postgresql:{POSTGRES_JDBC_VERSION}")
                implementation("com.auth0:java-jwt:{JAVA_JWT_VERSION}")
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

            // The database-backed scenario is opt-in: `gradle test` stays
            // offline and database free, and the runtime harness selects the
            // tagged scenario through the dedicated task below.
            tasks.test {{
                useJUnitPlatform {{ excludeTags("integration") }}
            }}

            tasks.register<Test>("integrationTest") {{
                testClassesDirs = sourceSets["test"].output.classesDirs
                classpath = sourceSets["test"].runtimeClasspath
                useJUnitPlatform {{ includeTags("integration") }}
                outputs.upToDateWhen {{ false }}
            }}

            // Regenerate gradle.lockfile after changing any dependency:
            //   gradle --no-daemon --write-locks resolveAndLockAll
            // The lock must be produced by this exact build, because the test
            // framework variant kotlin("test") resolves to depends on the
            // useJUnitPlatform configuration above.
            tasks.register("resolveAndLockAll") {{
                doFirst {{ require(gradle.startParameter.isWriteDependencyLocks) }}
                doLast {{ configurations.filter {{ it.isCanBeResolved }}.forEach {{ it.resolve() }} }}
            }}
            """
        ),
        "gradle.lockfile": _production_lock(),
        "gradle.properties": clean(
            """
            org.gradle.caching=true
            org.gradle.daemon=false
            kotlin.code.style=official
            """
        ),
        f"src/main/kotlin/{package_path}/Security.kt": _security_source(request),
        f"src/main/kotlin/{package_path}/Store.kt": _store_source(request),
        f"src/main/kotlin/{package_path}/Application.kt": _application_source(request, port),
        f"src/test/kotlin/{package_path}/ProductionIntegrationTest.kt": _integration_test_source(request, port),
        f"src/test/kotlin/{package_path}/EnvironmentContractTest.kt": clean(
            f"""
            package {request.namespace}

            import kotlin.test.Test
            import kotlin.test.assertFailsWith
            import kotlin.test.assertTrue

            /** Offline guard that needs no database or key material. */
            class EnvironmentContractTest {{
                @Test
                fun requiredEnvironmentNamesTheMissingVariable() {{
                    val failure = assertFailsWith<IllegalStateException> {{
                        requiredEnvironment("ELMOS_DEFINITELY_NOT_SET")
                    }}
                    assertTrue(failure.message!!.contains("REQUIRED_ENVIRONMENT_MISSING"))
                }}
            }}
            """
        ),
        "scripts/local_runtime.py": render_local_runtime(
            auth_mode=request.auth_mode,
            app_command=["gradle", "--no-daemon", "--offline", "run"],
            verify_command=["gradle", "--no-daemon", "--offline", "integrationTest"],
        ),
        "openapi.yaml": openapi_yaml(request, server_port=port),
        "Dockerfile": clean(
            f"""
            FROM {GRADLE_IMAGE} AS build
            WORKDIR /workspace
            COPY . .
            RUN gradle --no-daemon installDist

            FROM {TEMURIN_JRE_IMAGE}
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
            name: kotlin-production-ci
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
                  - run: gradle --no-daemon test build
                  - run: python3 scripts/local_runtime.py --verify
            """
        ),
        "Makefile": clean(
            """
            .PHONY: test verify run build
            test:
            \tgradle --no-daemon test build
            verify:
            \tpython3 scripts/local_runtime.py --verify
            run:
            \tpython3 scripts/local_runtime.py
            build:
            \tgradle --no-daemon build
            """
        ),
        "README.md": target_readme(
            request,
            language=f"Kotlin {KOTLIN_VERSION} / JVM 21",
            framework=f"Ktor {KTOR_VERSION} + PostgreSQL JDBC",
            port=port,
            commands=(
                "gradle --no-daemon test build\n"
                "python3 scripts/local_runtime.py --verify\n"
                "python3 scripts/local_runtime.py"
            ),
        ),
    }
