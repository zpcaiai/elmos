# ruff: noqa: E501
"""ASP.NET Core production profile: PostgreSQL, forced RLS, JWT or OIDC bearer.

Same shared contract and harness as the Python, Java, Go and TypeScript
profiles. Token verification uses Microsoft.IdentityModel directly rather than
the ASP.NET authentication middleware, so the issuer, audience, expiry and
tenant-claim checks are all visible in one place instead of spread across
options objects.
"""
from __future__ import annotations

import json
from html import escape

from .container_images import DOTNET_ASPNET_IMAGE, DOTNET_SDK_IMAGE
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
    clean,
    dockerignore,
    env_example,
    gitignore,
    kubernetes_yaml,
    openapi_yaml,
    pretty_json,
    target_readme,
)

NAMESPACE = "Generated.Api"


def _csharp_type(field: FieldSpec) -> str:
    return {
        "string": "string",
        "integer": "long",
        "number": "double",
        "boolean": "bool",
        "datetime": "DateTimeOffset",
    }[field.type]


def _reader(field: FieldSpec, index: int) -> str:
    return {
        "string": f"reader.GetString({index})",
        "integer": f"reader.GetInt64({index})",
        "number": f"(double)reader.GetDecimal({index})",
        "boolean": f"reader.GetBoolean({index})",
        "datetime": f"reader.GetFieldValue<DateTimeOffset>({index})",
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
    if request.auth_mode == "jwt":
        key_setup = f"""
        var secret = File.ReadAllText(RequiredEnvironment("{ENV_JWT_SECRET_FILE}")).Trim();
        if (secret.Length < 32)
        {{
            throw new InvalidOperationException("JWT_SECRET_TOO_SHORT");
        }}
        _key = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(secret));
        _algorithm = SecurityAlgorithms.HmacSha256;
        """
    else:
        key_setup = f"""
        var jwks = new JsonWebKeySet(File.ReadAllText(RequiredEnvironment("{ENV_OIDC_JWKS_FILE}")));
        if (jwks.Keys.Count != 1)
        {{
            throw new InvalidOperationException("OIDC_JWKS_MUST_CONTAIN_EXACTLY_ONE_KEY");
        }}
        _key = jwks.Keys[0];
        _algorithm = SecurityAlgorithms.RsaSha256;
        """
    key_setup = clean(key_setup).rstrip().replace("\n", "\n        ")
    return clean(
        f"""
        using System.IdentityModel.Tokens.Jwt;
        using System.Text;
        using Microsoft.IdentityModel.Tokens;

        namespace {NAMESPACE};

        /// <summary>
        /// Bearer verification for the production profile.
        /// </summary>
        /// <remarks>
        /// A structurally valid signature is not authorization. The issuer,
        /// audience, expiry and the tenant claim the database policy is keyed
        /// on are all mandatory, so a token minted for another service or
        /// another tenant is refused here rather than becoming a cross-tenant
        /// read.
        /// </remarks>
        public sealed class TenantAuthenticator
        {{
            private readonly SecurityKey _key;
            private readonly string _algorithm;
            private readonly string _issuer;
            private readonly string _audience;
            private readonly JwtSecurityTokenHandler _handler = new();

            public TenantAuthenticator()
            {{
                {key_setup}
                _issuer = RequiredEnvironment("{ENV_AUTH_ISSUER}");
                _audience = RequiredEnvironment("{ENV_AUTH_AUDIENCE}");
            }}

            public static string RequiredEnvironment(string name)
            {{
                var value = Environment.GetEnvironmentVariable(name);
                if (string.IsNullOrWhiteSpace(value))
                {{
                    throw new InvalidOperationException($"REQUIRED_ENVIRONMENT_MISSING:{{name}}");
                }}

                return value;
            }}

            public string? TenantFrom(string? authorization)
            {{
                if (authorization is null || !authorization.StartsWith("Bearer ", StringComparison.Ordinal))
                {{
                    return null;
                }}

                var parameters = new TokenValidationParameters
                {{
                    ValidateIssuer = true,
                    ValidIssuer = _issuer,
                    ValidateAudience = true,
                    ValidAudience = _audience,
                    ValidateLifetime = true,
                    RequireExpirationTime = true,
                    ValidateIssuerSigningKey = true,
                    IssuerSigningKey = _key,
                    ValidAlgorithms = new[] {{ _algorithm }},
                    ClockSkew = TimeSpan.Zero,
                }};

                try
                {{
                    var principal = _handler.ValidateToken(
                        authorization["Bearer ".Length..],
                        parameters,
                        out _);
                    var tenant = principal.FindFirst("{TENANT_CLAIM}")?.Value;
                    return string.IsNullOrWhiteSpace(tenant) ? null : tenant;
                }}
                catch (Exception exception) when (
                    exception is SecurityTokenException or ArgumentException or FormatException)
                {{
                    return null;
                }}
            }}
        }}
        """
    )


def _store_source(request: SynthesisRequest) -> str:
    entity = request.entities[0]
    entity_class = pascal(entity.singular)
    sql = all_entity_sql(request, placeholder="${}")[0]
    properties = "\n    ".join(
        f"public {_csharp_type(field)} {pascal(field.name)} {{ get; init; }}"
        + (" = string.Empty;" if field.type == "string" else "")
        for field in entity.fields
    )
    # The id column is always the first projected column and is always read as
    # a string; only the declared fields need type-directed readers.
    read_arguments = ",\n                    ".join(
        ["Id = reader.GetGuid(0).ToString()"]
        + [
            f"{pascal(field.name)} = {_reader(field, index + 1)}"
            for index, field in enumerate(entity.fields)
        ]
    )
    # The generated SQL uses positional placeholders ($1, $2, ...), so every
    # parameter must be added positionally. Mixing a named parameter into a
    # positional command makes Npgsql fail at execution time.
    upsert_parameters = "\n                    ".join(
        f"command.Parameters.AddWithValue(payload.{pascal(field.name)});"
        for field in entity.fields
    )
    return clean(
        f"""
        using System.Data;
        using Npgsql;

        namespace {NAMESPACE};

        public sealed record {entity_class}Upsert
        {{
            {properties}
        }}

        public sealed record {entity_class}
        {{
            public string Id {{ get; init; }} = string.Empty;

            {properties}
        }}

        /// <summary>
        /// All statements run inside one tenant-scoped transaction.
        /// </summary>
        /// <remarks>
        /// {TENANT_SETTING} is applied with set_config(..., true) so it is
        /// transaction local and cannot leak to the next borrower of a pooled
        /// connection. Row level security is FORCED on every table, so that
        /// binding -- not the SQL text -- confines a request to its tenant.
        /// </remarks>
        public sealed class {entity_class}Store
        {{
            private readonly NpgsqlDataSource _dataSource;

            public {entity_class}Store(NpgsqlDataSource dataSource) => _dataSource = dataSource;

            private async Task<T> InTenantAsync<T>(
                string tenantId,
                Func<NpgsqlConnection, NpgsqlTransaction, Task<T>> work)
            {{
                if (string.IsNullOrWhiteSpace(tenantId))
                {{
                    throw new ArgumentException("TENANT_ID_REQUIRED", nameof(tenantId));
                }}

                await using var connection = await _dataSource.OpenConnectionAsync();
                await using var transaction = await connection.BeginTransactionAsync();
                await using (var bind = new NpgsqlCommand("SELECT set_config('{TENANT_SETTING}', $1, true)", connection, transaction))
                {{
                    bind.Parameters.AddWithValue(tenantId);
                    await bind.ExecuteNonQueryAsync();
                }}

                var result = await work(connection, transaction);
                await transaction.CommitAsync();
                return result;
            }}

            private static {entity_class} Read(NpgsqlDataReader reader) => new()
            {{
                {read_arguments}
            }};

            public Task<List<{entity_class}>> ListAsync(string tenantId) =>
                InTenantAsync(tenantId, async (connection, transaction) =>
                {{
                    var results = new List<{entity_class}>();
                    await using var command = new NpgsqlCommand({json.dumps(sql.list_sql)}, connection, transaction);
                    await using var reader = await command.ExecuteReaderAsync();
                    while (await reader.ReadAsync())
                    {{
                        results.Add(Read(reader));
                    }}

                    return results;
                }});

            public Task<{entity_class}?> FindAsync(string tenantId, Guid recordId) =>
                InTenantAsync(tenantId, async (connection, transaction) =>
                {{
                    await using var command = new NpgsqlCommand({json.dumps(sql.get_sql)}, connection, transaction);
                    command.Parameters.AddWithValue(recordId);
                    await using var reader = await command.ExecuteReaderAsync();
                    return await reader.ReadAsync() ? Read(reader) : null;
                }});

            public Task<{entity_class}> SaveAsync(string tenantId, Guid recordId, {entity_class}Upsert payload) =>
                InTenantAsync(tenantId, async (connection, transaction) =>
                {{
                    await using var command = new NpgsqlCommand({json.dumps(sql.upsert_sql)}, connection, transaction);
                    command.Parameters.AddWithValue(tenantId);
                    command.Parameters.AddWithValue(recordId);
                    {upsert_parameters}
                    await using var reader = await command.ExecuteReaderAsync();
                    if (!await reader.ReadAsync())
                    {{
                        throw new InvalidOperationException("UPSERT_RETURNED_NO_ROW");
                    }}

                    return Read(reader);
                }});

            public Task<bool> DeleteAsync(string tenantId, Guid recordId) =>
                InTenantAsync(tenantId, async (connection, transaction) =>
                {{
                    await using var command = new NpgsqlCommand({json.dumps(sql.delete_sql)}, connection, transaction);
                    command.Parameters.AddWithValue(recordId);
                    return await command.ExecuteNonQueryAsync() > 0;
                }});
        }}
        """
    )


def _program_source(request: SynthesisRequest, port: int) -> str:
    entity = request.entities[0]
    entity_class = pascal(entity.singular)
    required_checks = "\n    ".join(
        f'if (string.IsNullOrWhiteSpace(payload.{pascal(field.name)})) return Results.UnprocessableEntity(new {{ error = "PAYLOAD_INVALID" }});'
        for field in entity.fields
        if field.required and field.type == "string"
    ) or "_ = payload;"
    return clean(
        f"""
        using Npgsql;
        using {NAMESPACE};

        var builder = WebApplication.CreateBuilder(args);

        // The connection string arrives by file reference, never as an inline
        // setting, so it never appears in process arguments or config dumps.
        var databaseUrl = File.ReadAllText(
            TenantAuthenticator.RequiredEnvironment("{ENV_DATABASE_URL_FILE}")).Trim();
        if (!databaseUrl.StartsWith("postgresql://", StringComparison.Ordinal))
        {{
            throw new InvalidOperationException("DATABASE_URL_SCHEME_UNSUPPORTED");
        }}

        var uri = new Uri(databaseUrl);
        var credentials = uri.UserInfo.Split(':', 2);
        var connectionString = new NpgsqlConnectionStringBuilder
        {{
            Host = uri.Host,
            Port = uri.Port < 0 ? 5432 : uri.Port,
            Database = uri.AbsolutePath.TrimStart('/'),
            Username = credentials[0],
            Password = credentials.Length > 1 ? credentials[1] : string.Empty,
            SslMode = SslMode.Disable,
            MaxPoolSize = 8,
        }}.ToString();

        builder.Services.AddSingleton(NpgsqlDataSource.Create(connectionString));
        builder.Services.AddSingleton<TenantAuthenticator>();
        builder.Services.AddSingleton<{entity_class}Store>();

        var application = builder.Build();

        string? Tenant(HttpRequest request) =>
            application.Services.GetRequiredService<TenantAuthenticator>()
                .TenantFrom(request.Headers.Authorization.ToString());

        application.MapGet("/health", () => Results.Ok(new
        {{
            status = "UP",
            service = "{request.project_name}",
        }}));

        application.MapGet("/{entity.plural}", async (HttpRequest request, {entity_class}Store store) =>
        {{
            var tenant = Tenant(request);
            if (tenant is null) return Results.Json(new {{ error = "unauthorized" }}, statusCode: 401);
            return Results.Ok(await store.ListAsync(tenant));
        }});

        application.MapGet("/{entity.plural}/{{id}}", async (HttpRequest request, string id, {entity_class}Store store) =>
        {{
            var tenant = Tenant(request);
            if (tenant is null) return Results.Json(new {{ error = "unauthorized" }}, statusCode: 401);
            if (!Guid.TryParse(id, out var recordId))
            {{
                return Results.UnprocessableEntity(new {{ error = "RECORD_ID_MUST_BE_UUID" }});
            }}

            var record = await store.FindAsync(tenant, recordId);
            return record is null ? Results.NotFound(new {{ error = "not_found" }}) : Results.Ok(record);
        }});

        application.MapPut("/{entity.plural}/{{id}}", async (
            HttpRequest request,
            string id,
            {entity_class}Upsert payload,
            {entity_class}Store store) =>
        {{
            var tenant = Tenant(request);
            if (tenant is null) return Results.Json(new {{ error = "unauthorized" }}, statusCode: 401);
            if (!Guid.TryParse(id, out var recordId))
            {{
                return Results.UnprocessableEntity(new {{ error = "RECORD_ID_MUST_BE_UUID" }});
            }}

            {required_checks}
            return Results.Ok(await store.SaveAsync(tenant, recordId, payload));
        }});

        application.MapDelete("/{entity.plural}/{{id}}", async (HttpRequest request, string id, {entity_class}Store store) =>
        {{
            var tenant = Tenant(request);
            if (tenant is null) return Results.Json(new {{ error = "unauthorized" }}, statusCode: 401);
            if (!Guid.TryParse(id, out var recordId))
            {{
                return Results.UnprocessableEntity(new {{ error = "RECORD_ID_MUST_BE_UUID" }});
            }}

            await store.DeleteAsync(tenant, recordId);
            return Results.NoContent();
        }});

        application.Run($"http://{{Environment.GetEnvironmentVariable("HOST") ?? "0.0.0.0"}}:{{Environment.GetEnvironmentVariable("PORT") ?? "{port}"}}");

        public partial class Program {{ }}
        """
    )


def _integration_test_source(request: SynthesisRequest) -> str:
    entity = request.entities[0]
    body_json = json.dumps({field.name: _sample_json(field) for field in entity.fields})
    csharp_body = body_json.replace("\\", "\\\\").replace('"', '\\"')
    if request.auth_mode == "jwt":
        signer = f"""
        private static SigningCredentials Credentials(bool valid)
        {{
            var secret = valid
                ? File.ReadAllText(Environment.GetEnvironmentVariable("{ENV_JWT_SECRET_FILE}")!).Trim()
                : "an-entirely-different-secret-value-of-length";
            return new SigningCredentials(
                new SymmetricSecurityKey(Encoding.UTF8.GetBytes(secret)),
                SecurityAlgorithms.HmacSha256);
        }}
        """
    else:
        signer = f"""
        private static SigningCredentials Credentials(bool valid)
        {{
            RSA rsa;
            if (valid)
            {{
                rsa = RSA.Create();
                rsa.ImportFromPem(File.ReadAllText(
                    Environment.GetEnvironmentVariable("{ENV_OIDC_PRIVATE_KEY_FILE}")!));
            }}
            else
            {{
                rsa = RSA.Create(2048);
            }}

            return new SigningCredentials(
                new RsaSecurityKey(rsa) {{ KeyId = "elmos-local-integration" }},
                SecurityAlgorithms.RsaSha256);
        }}
        """
    signer = clean(signer).rstrip().replace("\n", "\n    ")
    return clean(
        f"""
        using System.IdentityModel.Tokens.Jwt;
        using System.Net;
        using System.Security.Claims;
        using System.Security.Cryptography;
        using System.Text;
        using Microsoft.IdentityModel.Tokens;
        using Xunit;

        namespace {NAMESPACE}.Tests;

        /// <summary>
        /// The ten-step scenario from production-contract.json, executed
        /// against the PostgreSQL instance the runtime harness provisioned.
        /// </summary>
        [Trait("Category", "Integration")]
        public sealed class ProductionIntegrationTests
        {{
            {signer}

            private static string Token(string? tenant, string issuer, string audience, bool valid)
            {{
                var claims = new List<Claim>
                {{
                    new(JwtRegisteredClaimNames.Sub, "integration-subject"),
                }};
                if (tenant is not null)
                {{
                    claims.Add(new Claim("{TENANT_CLAIM}", tenant));
                }}

                var token = new JwtSecurityToken(
                    issuer: issuer,
                    audience: audience,
                    claims: claims,
                    notBefore: DateTime.UtcNow.AddMinutes(-1),
                    expires: DateTime.UtcNow.AddMinutes(5),
                    signingCredentials: Credentials(valid));
                return new JwtSecurityTokenHandler().WriteToken(token);
            }}

            private static async Task<HttpResponseMessage> SendAsync(
                HttpClient client,
                HttpMethod method,
                string path,
                string? bearer,
                string? body)
            {{
                using var request = new HttpRequestMessage(method, path);
                if (bearer is not null)
                {{
                    request.Headers.TryAddWithoutValidation("Authorization", "Bearer " + bearer);
                }}

                if (body is not null)
                {{
                    request.Content = new StringContent(body, Encoding.UTF8, "application/json");
                }}

                return await client.SendAsync(request);
            }}

            [Fact]
            public async Task RunsTheSharedProductionScenario()
            {{
                var issuer = Environment.GetEnvironmentVariable("{ENV_AUTH_ISSUER}");
                var audience = Environment.GetEnvironmentVariable("{ENV_AUTH_AUDIENCE}");
                Assert.False(string.IsNullOrWhiteSpace(issuer), "integration environment is not provisioned");
                Assert.False(string.IsNullOrWhiteSpace(audience), "integration environment is not provisioned");

                var port = Environment.GetEnvironmentVariable("PORT") ?? "0";
                using var client = new HttpClient {{ BaseAddress = new Uri($"http://127.0.0.1:{{port}}") }};

                var tenantA = Token("tenant-a", issuer!, audience!, true);
                var tenantB = Token("tenant-b", issuer!, audience!, true);

                // health-unauthenticated
                Assert.Equal(HttpStatusCode.OK, (await SendAsync(client, HttpMethod.Get, "/health", null, null)).StatusCode);

                // missing-token-rejected
                Assert.Equal(HttpStatusCode.Unauthorized, (await SendAsync(client, HttpMethod.Get, "/{entity.plural}", null, null)).StatusCode);

                // bad-signature-rejected
                Assert.Equal(HttpStatusCode.Unauthorized, (await SendAsync(client, HttpMethod.Get, "/{entity.plural}", Token("tenant-a", issuer!, audience!, false), null)).StatusCode);

                // wrong-audience-rejected
                Assert.Equal(HttpStatusCode.Unauthorized, (await SendAsync(client, HttpMethod.Get, "/{entity.plural}", Token("tenant-a", issuer!, "another-service", true), null)).StatusCode);

                // wrong-issuer-rejected
                Assert.Equal(HttpStatusCode.Unauthorized, (await SendAsync(client, HttpMethod.Get, "/{entity.plural}", Token("tenant-a", "https://attacker.invalid/", audience!, true), null)).StatusCode);

                // missing-tenant-claim-rejected
                Assert.Equal(HttpStatusCode.Unauthorized, (await SendAsync(client, HttpMethod.Get, "/{entity.plural}", Token(null, issuer!, audience!, true), null)).StatusCode);

                // upsert-and-read
                var recordId = Guid.NewGuid().ToString();
                var created = await SendAsync(client, HttpMethod.Put, $"/{entity.plural}/{{recordId}}", tenantA, "{csharp_body}");
                Assert.Equal(HttpStatusCode.OK, created.StatusCode);
                var read = await SendAsync(client, HttpMethod.Get, $"/{entity.plural}/{{recordId}}", tenantA, null);
                Assert.Equal(HttpStatusCode.OK, read.StatusCode);
                Assert.Contains(recordId, await read.Content.ReadAsStringAsync(), StringComparison.Ordinal);

                // list-scoped-to-tenant
                var listed = await SendAsync(client, HttpMethod.Get, "/{entity.plural}", tenantA, null);
                Assert.Equal(HttpStatusCode.OK, listed.StatusCode);
                Assert.Contains(recordId, await listed.Content.ReadAsStringAsync(), StringComparison.Ordinal);

                // cross-tenant-read-blocked
                Assert.Equal(HttpStatusCode.NotFound, (await SendAsync(client, HttpMethod.Get, $"/{entity.plural}/{{recordId}}", tenantB, null)).StatusCode);
                var otherList = await SendAsync(client, HttpMethod.Get, "/{entity.plural}", tenantB, null);
                Assert.DoesNotContain(recordId, await otherList.Content.ReadAsStringAsync(), StringComparison.Ordinal);

                // delete-removes-record
                Assert.Equal(HttpStatusCode.NoContent, (await SendAsync(client, HttpMethod.Delete, $"/{entity.plural}/{{recordId}}", tenantA, null)).StatusCode);
                Assert.Equal(HttpStatusCode.NotFound, (await SendAsync(client, HttpMethod.Get, $"/{entity.plural}/{{recordId}}", tenantA, null)).StatusCode);
            }}
        }}
        """
    )


def render_dotnet_production(request: SynthesisRequest, port: int) -> dict[str, str]:
    if len(request.entities) != 1:
        raise ValueError(
            "DOTNET_PRODUCTION_PROFILE_SINGLE_ENTITY_ONLY:"
            + ",".join(entity.singular for entity in request.entities)
        )
    project_class = request.project_class
    api_project = f"{project_class}.Api"
    test_project = f"{project_class}.Api.Tests"

    integration_test = _integration_test_source(request).replace(
        'Environment.GetEnvironmentVariable("PORT") ?? "0"',
        f'Environment.GetEnvironmentVariable("PORT") ?? "{port}"',
    )

    return {
        ".gitignore": gitignore(),
        ".dockerignore": dockerignore(),
        ".env.example": env_example(request, port),
        "production-contract.json": pretty_json(production_contract(request)),
        "global.json": clean(
            """
            {
              "sdk": {
                "version": "10.0.301",
                "rollForward": "latestPatch",
                "allowPrerelease": false
              }
            }
            """
        ),
        "Directory.Build.props": clean(
            """
            <Project>
              <PropertyGroup>
                <TargetFramework>net10.0</TargetFramework>
                <Nullable>enable</Nullable>
                <ImplicitUsings>enable</ImplicitUsings>
                <TreatWarningsAsErrors>true</TreatWarningsAsErrors>
                <AnalysisLevel>latest</AnalysisLevel>
              </PropertyGroup>
            </Project>
            """
        ),
        "Directory.Packages.props": clean(
            """
            <Project>
              <PropertyGroup>
                <ManagePackageVersionsCentrally>true</ManagePackageVersionsCentrally>
              </PropertyGroup>
              <ItemGroup>
                <PackageVersion Include="Microsoft.IdentityModel.JsonWebTokens" Version="8.3.1" />
                <PackageVersion Include="Microsoft.NET.Test.Sdk" Version="18.8.1" />
                <PackageVersion Include="Npgsql" Version="9.0.3" />
                <PackageVersion Include="System.IdentityModel.Tokens.Jwt" Version="8.3.1" />
                <PackageVersion Include="xunit" Version="2.9.3" />
                <PackageVersion Include="xunit.runner.visualstudio" Version="3.1.5" />
              </ItemGroup>
            </Project>
            """
        ),
        f"{project_class}.slnx": clean(
            f"""
            <Solution>
              <Folder Name="/src/">
                <Project Path="src/{api_project}/{api_project}.csproj" />
              </Folder>
              <Folder Name="/tests/">
                <Project Path="tests/{test_project}/{test_project}.csproj" />
              </Folder>
            </Solution>
            """
        ),
        f"src/{api_project}/{api_project}.csproj": clean(
            f"""
            <Project Sdk="Microsoft.NET.Sdk.Web">
              <PropertyGroup>
                <RootNamespace>{NAMESPACE}</RootNamespace>
              </PropertyGroup>
              <ItemGroup>
                <PackageReference Include="Npgsql" />
                <PackageReference Include="System.IdentityModel.Tokens.Jwt" />
                <PackageReference Include="Microsoft.IdentityModel.JsonWebTokens" />
              </ItemGroup>
            </Project>
            """
        ),
        f"src/{api_project}/TenantAuthenticator.cs": _security_source(request),
        f"src/{api_project}/Store.cs": _store_source(request),
        f"src/{api_project}/Program.cs": _program_source(request, port),
        f"src/{api_project}/appsettings.json": pretty_json(
            {"Logging": {"LogLevel": {"Default": "Information", "Microsoft.AspNetCore": "Warning"}}}
        ),
        f"tests/{test_project}/{test_project}.csproj": clean(
            f"""
            <Project Sdk="Microsoft.NET.Sdk">
              <PropertyGroup>
                <IsPackable>false</IsPackable>
                <IsTestProject>true</IsTestProject>
                <RootNamespace>{NAMESPACE}.Tests</RootNamespace>
                <!--
                  The database-backed scenario needs a provisioned instance, so
                  a plain `dotnet test` excludes it. The runtime harness selects
                  it explicitly with a command-line filter, which overrides this.
                -->
                <VSTestTestCaseFilter>Category!=Integration</VSTestTestCaseFilter>
              </PropertyGroup>
              <ItemGroup>
                <PackageReference Include="Microsoft.NET.Test.Sdk" />
                <PackageReference Include="System.IdentityModel.Tokens.Jwt" />
                <PackageReference Include="xunit" />
                <PackageReference Include="xunit.runner.visualstudio">
                  <PrivateAssets>all</PrivateAssets>
                  <IncludeAssets>runtime; build; native; contentfiles; analyzers; buildtransitive</IncludeAssets>
                </PackageReference>
              </ItemGroup>
              <ItemGroup>
                <ProjectReference Include="../../src/{api_project}/{api_project}.csproj" />
              </ItemGroup>
            </Project>
            """
        ),
        f"tests/{test_project}/ProductionIntegrationTests.cs": integration_test,
        f"tests/{test_project}/TenantContractTests.cs": clean(
            f"""
            using Xunit;

            namespace {NAMESPACE}.Tests;

            /// <summary>Offline guards that need no database or key material.</summary>
            public sealed class TenantContractTests
            {{
                [Theory]
                [InlineData("REQUIRED_ENVIRONMENT_MISSING")]
                public void RequiredEnvironmentNamesTheMissingVariable(string expected)
                {{
                    var failure = Assert.Throws<InvalidOperationException>(
                        () => TenantAuthenticator.RequiredEnvironment("ELMOS_DEFINITELY_NOT_SET"));
                    Assert.Contains(expected, failure.Message, StringComparison.Ordinal);
                }}
            }}
            """
        ),
        "scripts/local_runtime.py": render_local_runtime(
            auth_mode=request.auth_mode,
            app_command=["dotnet", "run", "-c", "Release", "--project", f"src/{api_project}/{api_project}.csproj"],
            verify_command=[
                "dotnet",
                "test",
                "-c",
                "Release",
                "--filter",
                "Category=Integration",
            ],
        ),
        "openapi.yaml": openapi_yaml(request, server_port=port),
        "Dockerfile": clean(
            f"""
            FROM {DOTNET_SDK_IMAGE} AS build
            WORKDIR /workspace
            COPY . .
            RUN dotnet publish src/{api_project}/{api_project}.csproj -c Release -o /out

            FROM {DOTNET_ASPNET_IMAGE}
            WORKDIR /app
            COPY --from=build /out .
            USER $APP_UID
            EXPOSE {port}
            ENTRYPOINT ["dotnet", "{api_project}.dll"]
            """
        ),
        "deploy/kubernetes.yaml": kubernetes_yaml(request, language="csharp", port=port),
        ".github/workflows/ci.yml": clean(
            f"""
            name: dotnet-production-ci
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
                  - uses: actions/setup-dotnet@87b7050bc53ea08284295505d98d2aa94301e852 # v4
                    with:
                      dotnet-version: '10.0.301'
                  - run: dotnet restore {project_class}.slnx --use-lock-file
                  - run: dotnet test {project_class}.slnx --no-restore -c Release
                  - run: python3 scripts/local_runtime.py --verify
            """
        ),
        "Makefile": clean(
            """
            .PHONY: test verify run build
            test:
            \tdotnet test -c Release
            verify:
            \tpython3 scripts/local_runtime.py --verify
            run:
            \tpython3 scripts/local_runtime.py
            build:
            \tdotnet build -c Release
            """
        ),
        "README.md": target_readme(
            request,
            language="C# / .NET 10.0.301",
            framework="ASP.NET Core minimal API + Npgsql",
            port=port,
            commands=(
                "dotnet test -c Release\n"
                "python3 scripts/local_runtime.py --verify\n"
                "python3 scripts/local_runtime.py"
            ),
        ),
        "description.txt": escape(request.description) + "\n",
    }
