"""Spring Boot production profile: PostgreSQL, forced RLS, JWT or OIDC bearer.

This target satisfies the same ``production_contract`` the Python profile does,
against the same database provisioned by the same shared runtime harness. The
two implementations are therefore comparable: a difference in the integration
result is a difference in the application, not in the fixture.

Tenant isolation is enforced by the database, not by the query builder. Every
request opens one transaction, sets ``app.tenant_id`` as a *local* setting bound
to that transaction, and lets the forced row-level-security policy filter rows.
A missing or wrong tenant claim therefore cannot read another tenant's data even
if a future query forgets a predicate.
"""
from __future__ import annotations

import json
from html import escape

from .container_images import MAVEN_IMAGE, TEMURIN_JRE_IMAGE
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

JDBC_PLACEHOLDER = "?"


def _java_type(field: FieldSpec) -> str:
    return {
        "string": "String",
        "integer": "Long",
        "number": "Double",
        "boolean": "Boolean",
        "datetime": "java.time.OffsetDateTime",
    }[field.type]


def _result_getter(field: FieldSpec, index: int) -> str:
    accessor = {
        "string": f'row.getString({index})',
        "integer": f'row.getObject({index}, Long.class)',
        # pgjdbc cannot convert `numeric` to Double via getObject; read the
        # BigDecimal the wire type actually carries and narrow explicitly.
        "number": f'readNumber(row, {index})',
        "boolean": f'row.getObject({index}, Boolean.class)',
        "datetime": f'row.getObject({index}, java.time.OffsetDateTime.class)',
    }[field.type]
    return accessor


def _validation(field: FieldSpec) -> str:
    if not field.required:
        return ""
    return (
        "@jakarta.validation.constraints.NotBlank "
        if field.type == "string"
        else "@jakarta.validation.constraints.NotNull "
    )


def _security_source(request: SynthesisRequest) -> str:
    """Bearer verification bound to issuer, audience and the tenant claim."""
    if request.auth_mode == "jwt":
        decoder = clean(
            f"""
            var secretPath = requiredEnvironment("{ENV_JWT_SECRET_FILE}");
            byte[] secret;
            try {{
                secret = java.nio.file.Files.readString(java.nio.file.Path.of(secretPath))
                        .strip().getBytes(java.nio.charset.StandardCharsets.UTF_8);
            }} catch (java.io.IOException error) {{
                throw new IllegalStateException("JWT_SECRET_UNREADABLE", error);
            }}
            if (secret.length < 32) {{
                throw new IllegalStateException("JWT_SECRET_TOO_SHORT");
            }}
            var decoder = org.springframework.security.oauth2.jwt.NimbusJwtDecoder
                    .withSecretKey(new javax.crypto.spec.SecretKeySpec(secret, "HmacSHA256"))
                    .macAlgorithm(org.springframework.security.oauth2.jose.jws.MacAlgorithm.HS256)
                    .build();
            """
        )
    else:
        decoder = clean(
            f"""
            var jwksPath = requiredEnvironment("{ENV_OIDC_JWKS_FILE}");
            java.security.interfaces.RSAPublicKey publicKey;
            try {{
                var keys = com.nimbusds.jose.jwk.JWKSet.load(new java.io.File(jwksPath));
                if (keys.getKeys().size() != 1) {{
                    throw new IllegalStateException("OIDC_JWKS_MUST_CONTAIN_EXACTLY_ONE_KEY");
                }}
                publicKey = ((com.nimbusds.jose.jwk.RSAKey) keys.getKeys().get(0)).toRSAPublicKey();
            }} catch (IllegalStateException error) {{
                throw error;
            }} catch (Exception error) {{
                throw new IllegalStateException("OIDC_JWKS_UNREADABLE", error);
            }}
            var decoder = org.springframework.security.oauth2.jwt.NimbusJwtDecoder
                    .withPublicKey(publicKey)
                    .signatureAlgorithm(org.springframework.security.oauth2.jose.jws.SignatureAlgorithm.RS256)
                    .build();
            """
        )
    decoder = decoder.rstrip().replace("\n", "\n        ")
    return clean(
        f"""
        package {request.namespace}.security;

        import org.springframework.context.annotation.Bean;
        import org.springframework.context.annotation.Configuration;
        import org.springframework.security.config.annotation.web.builders.HttpSecurity;
        import org.springframework.security.config.http.SessionCreationPolicy;
        import org.springframework.security.oauth2.jwt.JwtDecoder;
        import org.springframework.security.web.SecurityFilterChain;

        import java.util.List;

        /**
         * Bearer verification for the production profile.
         *
         * <p>Signature validity alone is not authorization. A token is accepted
         * only when its issuer and audience match this deployment and it carries
         * the tenant claim the database policy is keyed on, so a valid token
         * minted for another service or another tenant is refused here rather
         * than becoming a cross-tenant read.
         */
        @Configuration
        public class SecurityConfiguration {{

            static String requiredEnvironment(String name) {{
                var value = System.getenv(name);
                if (value == null || value.isBlank()) {{
                    throw new IllegalStateException("REQUIRED_ENVIRONMENT_MISSING:" + name);
                }}
                return value;
            }}

            @Bean
            public JwtDecoder jwtDecoder() {{
                {decoder}
                var issuer = requiredEnvironment("{ENV_AUTH_ISSUER}");
                var audience = requiredEnvironment("{ENV_AUTH_AUDIENCE}");
                decoder.setJwtValidator(token -> {{
                    if (!issuer.equals(token.getIssuer() == null ? null : token.getIssuer().toString())) {{
                        return org.springframework.security.oauth2.core.OAuth2TokenValidatorResult.failure(
                                new org.springframework.security.oauth2.core.OAuth2Error("invalid_issuer"));
                    }}
                    List<String> audiences = token.getAudience();
                    if (audiences == null || !audiences.contains(audience)) {{
                        return org.springframework.security.oauth2.core.OAuth2TokenValidatorResult.failure(
                                new org.springframework.security.oauth2.core.OAuth2Error("invalid_audience"));
                    }}
                    var tenant = token.getClaimAsString("{TENANT_CLAIM}");
                    if (tenant == null || tenant.isBlank()) {{
                        return org.springframework.security.oauth2.core.OAuth2TokenValidatorResult.failure(
                                new org.springframework.security.oauth2.core.OAuth2Error("missing_tenant_claim"));
                    }}
                    if (token.getExpiresAt() == null) {{
                        return org.springframework.security.oauth2.core.OAuth2TokenValidatorResult.failure(
                                new org.springframework.security.oauth2.core.OAuth2Error("missing_expiry"));
                    }}
                    return org.springframework.security.oauth2.core.OAuth2TokenValidatorResult.success();
                }});
                return decoder;
            }}

            @Bean
            public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {{
                http
                    .csrf(csrf -> csrf.disable())
                    .sessionManagement(session ->
                        session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                    .authorizeHttpRequests(requests -> requests
                        .requestMatchers("/health", "/actuator/health").permitAll()
                        .anyRequest().authenticated())
                    .oauth2ResourceServer(server -> server.jwt(jwt -> {{ }}));
                return http.build();
            }}
        }}
        """
    )


def _tenant_template_source(request: SynthesisRequest) -> str:
    return clean(
        f"""
        package {request.namespace}.persistence;

        import org.springframework.stereotype.Component;

        import javax.sql.DataSource;
        import java.sql.Connection;
        import java.sql.PreparedStatement;
        import java.sql.SQLException;
        import java.util.function.Function;

        /**
         * Runs work inside one tenant-scoped transaction.
         *
         * <p>{TENANT_SETTING} is applied with SET LOCAL so it lives and dies with
         * the transaction and can never leak to the next borrower of a pooled
         * connection. Row-level security is FORCED on every table, so this
         * setting -- not the SQL text -- is what confines a request to its
         * tenant.
         */
        @Component
        public class TenantTemplate {{
            private final DataSource dataSource;

            public TenantTemplate(DataSource dataSource) {{
                this.dataSource = dataSource;
            }}

            public <T> T inTenant(String tenantId, Function<Connection, T> work) {{
                if (tenantId == null || tenantId.isBlank()) {{
                    throw new IllegalArgumentException("TENANT_ID_REQUIRED");
                }}
                try (Connection connection = dataSource.getConnection()) {{
                    boolean previousAutoCommit = connection.getAutoCommit();
                    connection.setAutoCommit(false);
                    try {{
                        try (PreparedStatement statement =
                                     connection.prepareStatement("SELECT set_config('{TENANT_SETTING}', ?, true)")) {{
                            statement.setString(1, tenantId);
                            statement.execute();
                        }}
                        T result = work.apply(connection);
                        connection.commit();
                        return result;
                    }} catch (RuntimeException error) {{
                        connection.rollback();
                        throw error;
                    }} finally {{
                        connection.setAutoCommit(previousAutoCommit);
                    }}
                }} catch (SQLException error) {{
                    throw new IllegalStateException("TENANT_TRANSACTION_FAILED", error);
                }}
            }}
        }}
        """
    )


def _datasource_source(request: SynthesisRequest) -> str:
    return clean(
        f"""
        package {request.namespace}.persistence;

        import com.zaxxer.hikari.HikariConfig;
        import com.zaxxer.hikari.HikariDataSource;
        import org.springframework.context.annotation.Bean;
        import org.springframework.context.annotation.Configuration;

        import javax.sql.DataSource;
        import java.io.IOException;
        import java.nio.file.Files;
        import java.nio.file.Path;

        /**
         * The database URL is read from a file reference, never from an inline
         * property, so the connection string does not appear in process
         * arguments, container specs or configuration dumps.
         */
        @Configuration
        public class DataSourceConfiguration {{

            @Bean
            public DataSource dataSource() {{
                var reference = System.getenv("{ENV_DATABASE_URL_FILE}");
                if (reference == null || reference.isBlank()) {{
                    throw new IllegalStateException("REQUIRED_ENVIRONMENT_MISSING:{ENV_DATABASE_URL_FILE}");
                }}
                String url;
                try {{
                    url = Files.readString(Path.of(reference)).strip();
                }} catch (IOException error) {{
                    throw new IllegalStateException("DATABASE_URL_UNREADABLE", error);
                }}
                if (!url.startsWith("postgresql://")) {{
                    throw new IllegalStateException("DATABASE_URL_SCHEME_UNSUPPORTED");
                }}
                // The harness publishes a standard credentialed URL
                // (postgresql://user:pass@127.0.0.1:port/db). JDBC does not read
                // userinfo from its URL, so credentials are split out here and
                // handed to the pool as properties instead.
                java.net.URI parsed;
                try {{
                    parsed = java.net.URI.create(url);
                }} catch (IllegalArgumentException error) {{
                    throw new IllegalStateException("DATABASE_URL_UNPARSEABLE", error);
                }}
                var host = parsed.getHost();
                var database = parsed.getPath() == null ? "" : parsed.getPath().replaceFirst("^/", "");
                if (host == null || database.isBlank()) {{
                    throw new IllegalStateException("DATABASE_URL_HOST_OR_DATABASE_MISSING");
                }}
                var port = parsed.getPort() < 0 ? 5432 : parsed.getPort();
                var config = new HikariConfig();
                config.setJdbcUrl("jdbc:postgresql://" + host + ":" + port + "/" + database);
                var userInfo = parsed.getUserInfo();
                if (userInfo != null && !userInfo.isBlank()) {{
                    var separator = userInfo.indexOf(':');
                    config.setUsername(separator < 0 ? userInfo : userInfo.substring(0, separator));
                    if (separator >= 0) {{
                        config.setPassword(userInfo.substring(separator + 1));
                    }}
                }}
                config.setMaximumPoolSize(8);
                config.setMinimumIdle(1);
                config.setPoolName("{request.project_name}-pool");
                return new HikariDataSource(config);
            }}
        }}
        """
    )


def _integration_test_source(request: SynthesisRequest) -> str:
    entity = request.entities[0]
    body_fields = ", ".join(
        f'"{field.name}": {json.dumps(_sample_json(field))}' for field in entity.fields
    )
    body_json = "{" + body_fields + "}"
    java_body = body_json.replace("\\", "\\\\").replace('"', '\\"')

    if request.auth_mode == "jwt":
        signer = clean(
            f"""
            var secret = java.nio.file.Files.readString(
                    java.nio.file.Path.of(required("{ENV_JWT_SECRET_FILE}"))).strip();
            var signer = new com.nimbusds.jose.crypto.MACSigner(
                    secret.getBytes(java.nio.charset.StandardCharsets.UTF_8));
            var header = new com.nimbusds.jose.JWSHeader(com.nimbusds.jose.JWSAlgorithm.HS256);
            var wrongSigner = new com.nimbusds.jose.crypto.MACSigner(
                    "an-entirely-different-secret-value-of-length".getBytes(
                            java.nio.charset.StandardCharsets.UTF_8));
            """
        )
    else:
        signer = clean(
            f"""
            var pem = java.nio.file.Files.readString(
                    java.nio.file.Path.of(required("{ENV_OIDC_PRIVATE_KEY_FILE}")));
            var der = java.util.Base64.getDecoder().decode(pem
                    .replace("-----BEGIN PRIVATE KEY-----", "")
                    .replace("-----END PRIVATE KEY-----", "")
                    .replaceAll("\\\\s", ""));
            var privateKey = (java.security.interfaces.RSAPrivateKey) java.security.KeyFactory
                    .getInstance("RSA")
                    .generatePrivate(new java.security.spec.PKCS8EncodedKeySpec(der));
            var signer = new com.nimbusds.jose.crypto.RSASSASigner(privateKey);
            var header = new com.nimbusds.jose.JWSHeader.Builder(com.nimbusds.jose.JWSAlgorithm.RS256)
                    .keyID("elmos-local-integration").build();
            var otherKey = java.security.KeyPairGenerator.getInstance("RSA");
            otherKey.initialize(2048);
            var wrongSigner = new com.nimbusds.jose.crypto.RSASSASigner(
                    (java.security.interfaces.RSAPrivateKey) otherKey.generateKeyPair().getPrivate());
            """
        )
    signer = signer.rstrip().replace("\n", "\n        ")

    return clean(
        f"""
        package {request.namespace};

        import org.junit.jupiter.api.Tag;
        import org.junit.jupiter.api.Test;
        import org.springframework.beans.factory.annotation.Autowired;
        import org.springframework.boot.test.context.SpringBootTest;
        import org.springframework.boot.test.web.server.LocalServerPort;

        import java.net.URI;
        import java.net.http.HttpClient;
        import java.net.http.HttpRequest;
        import java.net.http.HttpResponse;
        import java.util.UUID;

        import static org.junit.jupiter.api.Assertions.assertEquals;
        import static org.junit.jupiter.api.Assertions.assertTrue;

        /**
         * The shared production integration scenario, executed against the real
         * PostgreSQL instance provisioned by scripts/local_runtime.py.
         *
         * <p>Tagged "integration" so an ordinary `mvn -B test` stays offline and
         * database free; the harness runs this tag explicitly after provisioning.
         */
        @Tag("integration")
        @SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
        class ProductionIntegrationTest {{

            @LocalServerPort
            int port;

            private final HttpClient client = HttpClient.newHttpClient();

            private static String required(String name) {{
                var value = System.getenv(name);
                assertTrue(value != null && !value.isBlank(), "missing environment " + name);
                return value;
            }}

            private String token(String tenant, String issuer, String audience, boolean valid) throws Exception {{
                {signer}
                var claims = new com.nimbusds.jwt.JWTClaimsSet.Builder()
                        .issuer(issuer)
                        .audience(audience)
                        .subject("integration-subject")
                        .expirationTime(new java.util.Date(System.currentTimeMillis() + 300_000))
                        .issueTime(new java.util.Date());
                if (tenant != null) {{
                    claims.claim("{TENANT_CLAIM}", tenant);
                }}
                var jwt = new com.nimbusds.jwt.SignedJWT(header, claims.build());
                jwt.sign(valid ? signer : wrongSigner);
                return jwt.serialize();
            }}

            private String validToken(String tenant) throws Exception {{
                return token(tenant, required("{ENV_AUTH_ISSUER}"), required("{ENV_AUTH_AUDIENCE}"), true);
            }}

            private HttpResponse<String> send(String method, String path, String bearer, String body)
                    throws Exception {{
                var builder = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + path));
                if (bearer != null) {{
                    builder.header("Authorization", "Bearer " + bearer);
                }}
                if (body == null) {{
                    builder.method(method, HttpRequest.BodyPublishers.noBody());
                }} else {{
                    builder.header("Content-Type", "application/json")
                            .method(method, HttpRequest.BodyPublishers.ofString(body));
                }}
                return client.send(builder.build(), HttpResponse.BodyHandlers.ofString());
            }}

            @Test
            void runsTheSharedProductionScenario() throws Exception {{
                var issuer = required("{ENV_AUTH_ISSUER}");
                var audience = required("{ENV_AUTH_AUDIENCE}");

                // health-unauthenticated
                assertEquals(200, send("GET", "/health", null, null).statusCode());

                // missing-token-rejected
                assertEquals(401, send("GET", "/{entity.plural}", null, null).statusCode());

                // bad-signature-rejected
                assertEquals(401, send("GET", "/{entity.plural}",
                        token("tenant-a", issuer, audience, false), null).statusCode());

                // wrong-audience-rejected
                assertEquals(401, send("GET", "/{entity.plural}",
                        token("tenant-a", issuer, "another-service", true), null).statusCode());

                // wrong-issuer-rejected
                assertEquals(401, send("GET", "/{entity.plural}",
                        token("tenant-a", "https://attacker.invalid/", audience, true), null).statusCode());

                // missing-tenant-claim-rejected
                assertEquals(401, send("GET", "/{entity.plural}",
                        token(null, issuer, audience, true), null).statusCode());

                // upsert-and-read
                var recordId = UUID.randomUUID().toString();
                var tenantA = validToken("tenant-a");
                var created = send("PUT", "/{entity.plural}/" + recordId, tenantA, "{java_body}");
                assertEquals(200, created.statusCode(), created.body());
                var read = send("GET", "/{entity.plural}/" + recordId, tenantA, null);
                assertEquals(200, read.statusCode());
                assertTrue(read.body().contains(recordId));

                // list-scoped-to-tenant
                var listed = send("GET", "/{entity.plural}", tenantA, null);
                assertEquals(200, listed.statusCode());
                assertTrue(listed.body().contains(recordId));

                // cross-tenant-read-blocked
                var tenantB = validToken("tenant-b");
                assertEquals(404, send("GET", "/{entity.plural}/" + recordId, tenantB, null).statusCode());
                assertTrue(!send("GET", "/{entity.plural}", tenantB, null).body().contains(recordId));

                // delete-removes-record
                assertEquals(204, send("DELETE", "/{entity.plural}/" + recordId, tenantA, null).statusCode());
                assertEquals(404, send("GET", "/{entity.plural}/" + recordId, tenantA, null).statusCode());
            }}
        }}
        """
    )


def _sample_json(field: FieldSpec) -> object:
    return {
        "string": f"sample-{field.name}",
        "integer": 1,
        "number": 1.5,
        "boolean": True,
        "datetime": "2026-01-01T00:00:00Z",
    }[field.type]


def _pom(request: SynthesisRequest) -> str:
    return clean(
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
          <artifactId>{request.project_name}</artifactId>
          <version>1.0.0-SNAPSHOT</version>
          <name>{request.project_name}</name>
          <description>{escape(request.description)}</description>
          <properties>
            <java.version>21</java.version>
            <!--
              Tag selection is expressed as properties so the integration profile
              can override it. Inline plugin configuration would win over both
              profile configuration and command-line properties, which silently
              yields an empty tag intersection and a green "0 tests" run.
            -->
            <elmos.surefire.excludedGroups>integration</elmos.surefire.excludedGroups>
            <elmos.surefire.groups></elmos.surefire.groups>
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
              <artifactId>spring-boot-starter-jdbc</artifactId>
            </dependency>
            <dependency>
              <groupId>org.springframework.boot</groupId>
              <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
            </dependency>
            <dependency>
              <groupId>org.postgresql</groupId>
              <artifactId>postgresql</artifactId>
              <scope>runtime</scope>
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
              <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <configuration>
                  <excludedGroups>${{elmos.surefire.excludedGroups}}</excludedGroups>
                  <groups>${{elmos.surefire.groups}}</groups>
                </configuration>
              </plugin>
            </plugins>
          </build>
          <profiles>
            <!--
              The database-backed scenario is opt-in. A plain `mvn -B test` stays
              offline and database free; the runtime harness activates this
              profile after it has provisioned PostgreSQL and signing material.
            -->
            <profile>
              <id>integration</id>
              <properties>
                <elmos.surefire.excludedGroups></elmos.surefire.excludedGroups>
                <elmos.surefire.groups>integration</elmos.surefire.groups>
              </properties>
            </profile>
          </profiles>
        </project>
        """
    )


def render_java_production(request: SynthesisRequest, port: int) -> dict[str, str]:
    package_path = request.namespace.replace(".", "/")
    app_class = f"{request.project_class}Application"
    statements = {item.entity: item for item in all_entity_sql(request, placeholder=JDBC_PLACEHOLDER)}

    files: dict[str, str] = {
        ".gitignore": gitignore(),
        ".dockerignore": dockerignore(),
        ".env.example": env_example(request, port),
        "pom.xml": _pom(request),
        "production-contract.json": pretty_json(production_contract(request)),
        f"src/main/java/{package_path}/{app_class}.java": clean(
            f"""
            package {request.namespace};

            import org.springframework.boot.SpringApplication;
            import org.springframework.boot.autoconfigure.SpringBootApplication;
            import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;

            @SpringBootApplication(exclude = {{DataSourceAutoConfiguration.class}})
            public class {app_class} {{
                public static void main(String[] args) {{
                    SpringApplication.run({app_class}.class, args);
                }}
            }}
            """
        ),
        f"src/main/java/{package_path}/security/SecurityConfiguration.java": _security_source(request),
        f"src/main/java/{package_path}/security/TenantIdentity.java": clean(
            f"""
            package {request.namespace}.security;

            import org.springframework.security.core.context.SecurityContextHolder;
            import org.springframework.security.oauth2.jwt.Jwt;

            /** The caller's tenant, taken only from the verified token. */
            public final class TenantIdentity {{
                private TenantIdentity() {{
                }}

                public static String current() {{
                    var authentication = SecurityContextHolder.getContext().getAuthentication();
                    if (authentication == null || !(authentication.getPrincipal() instanceof Jwt jwt)) {{
                        throw new IllegalStateException("TENANT_IDENTITY_UNAVAILABLE");
                    }}
                    var tenant = jwt.getClaimAsString("{TENANT_CLAIM}");
                    if (tenant == null || tenant.isBlank()) {{
                        throw new IllegalStateException("TENANT_IDENTITY_UNAVAILABLE");
                    }}
                    return tenant;
                }}
            }}
            """
        ),
        f"src/main/java/{package_path}/persistence/DataSourceConfiguration.java": _datasource_source(request),
        f"src/main/java/{package_path}/persistence/TenantTemplate.java": _tenant_template_source(request),
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
              address: ${{SERVER_ADDRESS:0.0.0.0}}
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
        f"src/test/java/{package_path}/ProductionIntegrationTest.java": _integration_test_source(request),
        f"src/test/java/{package_path}/TenantTemplateContractTest.java": clean(
            f"""
            package {request.namespace};

            import {request.namespace}.persistence.TenantTemplate;
            import org.junit.jupiter.api.Test;

            import static org.junit.jupiter.api.Assertions.assertThrows;

            /** Offline guards that need no database. */
            class TenantTemplateContractTest {{
                @Test
                void refusesABlankTenant() {{
                    var template = new TenantTemplate(null);
                    assertThrows(IllegalArgumentException.class, () -> template.inTenant("", connection -> null));
                    assertThrows(IllegalArgumentException.class, () -> template.inTenant(null, connection -> null));
                }}
            }}
            """
        ),
        "scripts/local_runtime.py": render_local_runtime(
            auth_mode=request.auth_mode,
            app_command=["mvn", "-B", "-q", "spring-boot:run"],
            verify_command=["mvn", "-B", "test", "-Pintegration"],
        ),
        "openapi.yaml": openapi_yaml(request, server_port=port),
        "Dockerfile": clean(
            f"""
            FROM {MAVEN_IMAGE} AS build
            WORKDIR /workspace
            COPY pom.xml ./
            RUN mvn -B -DskipTests dependency:go-offline
            COPY src ./src
            RUN mvn -B -DskipTests package

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
            name: java-production-ci
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
                  # The database-backed scenario requires a provisioned PostgreSQL
                  # instance and local signing material, so it runs through the
                  # runtime harness rather than as a plain Maven goal.
                  - run: python3 scripts/local_runtime.py --verify
            """
        ),
        "Makefile": clean(
            """
            .PHONY: test verify run package
            test:
            \tmvn -B test
            verify:
            \tpython3 scripts/local_runtime.py --verify
            run:
            \tpython3 scripts/local_runtime.py
            package:
            \tmvn -B -DskipTests package
            """
        ),
        "README.md": target_readme(
            request,
            language="Java 21",
            framework="Spring Boot 3.5.3",
            port=port,
            commands=(
                "mvn -B test\n"
                "python3 scripts/local_runtime.py --verify\n"
                "python3 scripts/local_runtime.py"
            ),
        ),
    }

    for entity in request.entities:
        entity_class = pascal(entity.singular)
        upsert_class = f"Upsert{entity_class}Request"
        sql = statements[entity.singular]
        record_fields = ",\n        ".join(
            f"{_validation(field)}{_java_type(field)} {camel(field.name)}" for field in entity.fields
        )
        entity_fields = ",\n        ".join(
            ["String id", *(f"{_java_type(field)} {camel(field.name)}" for field in entity.fields)]
        )
        row_reads = ",\n                            ".join(
            ["row.getString(1)", *(_result_getter(field, index + 2) for index, field in enumerate(entity.fields))]
        )
        bind_upsert = "\n                    ".join(
            f"statement.setObject({index + 3}, request.{camel(field.name)}());"
            for index, field in enumerate(entity.fields)
        )
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
                f"src/main/java/{package_path}/api/{upsert_class}.java": clean(
                    f"""
                    package {request.namespace}.api;

                    public record {upsert_class}(
                            {record_fields}
                    ) {{}}
                    """
                ),
                f"src/main/java/{package_path}/persistence/{entity_class}Repository.java": clean(
                    f"""
                    package {request.namespace}.persistence;

                    import {request.namespace}.api.{entity_class};
                    import {request.namespace}.api.Upsert{entity_class}Request;
                    import org.springframework.stereotype.Repository;

                    import java.sql.SQLException;
                    import java.util.ArrayList;
                    import java.util.List;
                    import java.util.Optional;

                    /**
                     * All four statements run inside {{@link TenantTemplate}}, so the
                     * database policy filters rows even though the SQL carries no
                     * tenant predicate of its own.
                     */
                    @Repository
                    public class {entity_class}Repository {{
                        private final TenantTemplate template;

                        public {entity_class}Repository(TenantTemplate template) {{
                            this.template = template;
                        }}

                        private static Double readNumber(java.sql.ResultSet row, int index) throws SQLException {{
                            var value = row.getBigDecimal(index);
                            return value == null ? null : value.doubleValue();
                        }}

                        public List<{entity_class}> list(String tenantId) {{
                            return template.inTenant(tenantId, connection -> {{
                                var results = new ArrayList<{entity_class}>();
                                try (var statement = connection.prepareStatement({json.dumps(sql.list_sql)});
                                     var row = statement.executeQuery()) {{
                                    while (row.next()) {{
                                        results.add(new {entity_class}(
                                            {row_reads}
                                        ));
                                    }}
                                }} catch (SQLException error) {{
                                    throw new IllegalStateException("QUERY_FAILED", error);
                                }}
                                return results;
                            }});
                        }}

                        public Optional<{entity_class}> find(String tenantId, String recordId) {{
                            return template.inTenant(tenantId, connection -> {{
                                try (var statement = connection.prepareStatement({json.dumps(sql.get_sql)})) {{
                                    statement.setObject(1, java.util.UUID.fromString(recordId));
                                    try (var row = statement.executeQuery()) {{
                                        if (!row.next()) {{
                                            return Optional.<{entity_class}>empty();
                                        }}
                                        return Optional.of(new {entity_class}(
                                            {row_reads}
                                        ));
                                    }}
                                }} catch (SQLException error) {{
                                    throw new IllegalStateException("QUERY_FAILED", error);
                                }}
                            }});
                        }}

                        public {entity_class} save(
                                String tenantId, String recordId, Upsert{entity_class}Request request) {{
                            return template.inTenant(tenantId, connection -> {{
                                try (var statement = connection.prepareStatement({json.dumps(sql.upsert_sql)})) {{
                                    statement.setString(1, tenantId);
                                    statement.setObject(2, java.util.UUID.fromString(recordId));
                                    {bind_upsert}
                                    try (var row = statement.executeQuery()) {{
                                        if (!row.next()) {{
                                            throw new IllegalStateException("UPSERT_RETURNED_NO_ROW");
                                        }}
                                        return new {entity_class}(
                                            {row_reads}
                                        );
                                    }}
                                }} catch (SQLException error) {{
                                    throw new IllegalStateException("QUERY_FAILED", error);
                                }}
                            }});
                        }}

                        public boolean delete(String tenantId, String recordId) {{
                            return template.inTenant(tenantId, connection -> {{
                                try (var statement = connection.prepareStatement({json.dumps(sql.delete_sql)})) {{
                                    statement.setObject(1, java.util.UUID.fromString(recordId));
                                    return statement.executeUpdate() > 0;
                                }} catch (SQLException error) {{
                                    throw new IllegalStateException("QUERY_FAILED", error);
                                }}
                            }});
                        }}
                    }}
                    """
                ),
                f"src/main/java/{package_path}/api/{entity_class}Controller.java": clean(
                    f"""
                    package {request.namespace}.api;

                    import {request.namespace}.persistence.{entity_class}Repository;
                    import {request.namespace}.security.TenantIdentity;
                    import jakarta.validation.Valid;
                    import org.springframework.http.ResponseEntity;
                    import org.springframework.web.bind.annotation.DeleteMapping;
                    import org.springframework.web.bind.annotation.GetMapping;
                    import org.springframework.web.bind.annotation.PathVariable;
                    import org.springframework.web.bind.annotation.PutMapping;
                    import org.springframework.web.bind.annotation.RequestBody;
                    import org.springframework.web.bind.annotation.RequestMapping;
                    import org.springframework.web.bind.annotation.RestController;

                    import java.util.List;
                    import java.util.UUID;

                    @RestController
                    @RequestMapping("/{entity.plural}")
                    public class {entity_class}Controller {{
                        private final {entity_class}Repository repository;

                        public {entity_class}Controller({entity_class}Repository repository) {{
                            this.repository = repository;
                        }}

                        private static String requireUuid(String value) {{
                            try {{
                                return UUID.fromString(value).toString();
                            }} catch (IllegalArgumentException error) {{
                                throw new org.springframework.web.server.ResponseStatusException(
                                        org.springframework.http.HttpStatus.UNPROCESSABLE_ENTITY,
                                        "RECORD_ID_MUST_BE_UUID");
                            }}
                        }}

                        @GetMapping
                        public List<{entity_class}> list() {{
                            return repository.list(TenantIdentity.current());
                        }}

                        @GetMapping("/{{id}}")
                        public ResponseEntity<{entity_class}> get(@PathVariable String id) {{
                            return repository.find(TenantIdentity.current(), requireUuid(id))
                                    .map(ResponseEntity::ok)
                                    .orElseGet(() -> ResponseEntity.notFound().build());
                        }}

                        @PutMapping("/{{id}}")
                        public {entity_class} put(
                                @PathVariable String id,
                                @Valid @RequestBody Upsert{entity_class}Request request) {{
                            return repository.save(TenantIdentity.current(), requireUuid(id), request);
                        }}

                        @DeleteMapping("/{{id}}")
                        public ResponseEntity<Void> delete(@PathVariable String id) {{
                            repository.delete(TenantIdentity.current(), requireUuid(id));
                            return ResponseEntity.noContent().build();
                        }}
                    }}
                    """
                ),
            }
        )
    return files
