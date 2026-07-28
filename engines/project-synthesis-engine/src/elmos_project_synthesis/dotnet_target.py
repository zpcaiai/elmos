from __future__ import annotations

import json

from .container_images import DOTNET_ASPNET_IMAGE, DOTNET_SDK_IMAGE
from .models import EntitySpec, FieldSpec, SynthesisRequest, pascal
from .rendering import (
    clean,
    dockerignore,
    env_example,
    gitignore,
    kubernetes_yaml,
    openapi_yaml,
    pascal_identifier,
    sample_payload,
    target_readme,
)


def _csharp_type(field: FieldSpec) -> str:
    base = {
        "string": "string",
        "integer": "long",
        "number": "double",
        "boolean": "bool",
        "datetime": "DateTimeOffset",
    }[field.type]
    if not field.required:
        return f"{base}?"
    return base


def render_dotnet(request: SynthesisRequest, port: int) -> dict[str, str]:
    if request.requires_database or request.requires_authentication:
        from .dotnet_production_target import render_dotnet_production

        return render_dotnet_production(request, port)
    project_class = request.project_class
    api_project = f"{project_class}.Api"
    test_project = f"{project_class}.Api.Tests"
    model_blocks: list[str] = []
    store_blocks: list[str] = []
    route_blocks: list[str] = []
    test_blocks: list[str] = []

    def csharp_sample(entity: EntitySpec) -> str:
        sample_values = sample_payload(request, entity)
        values: list[str] = []
        for field in entity.fields:
            value = sample_values[field.name]
            if field.type == "string":
                rendered = json.dumps(value, ensure_ascii=False)
            elif field.type in {"integer", "number"}:
                rendered = str(value)
            elif field.type == "boolean":
                rendered = str(value).lower()
            else:
                rendered = f'DateTimeOffset.Parse("{value}")'
            values.append(f"{pascal_identifier(field.name)} = {rendered}")
        return "new { " + ", ".join(values) + " }"

    for entity in request.entities:
        entity_class = pascal(entity.singular)
        entity_type = f"global::Generated.Api.{entity_class}"
        upsert_type = f"global::Generated.Api.{entity_class}Upsert"
        field_declarations = ",\n    ".join(
            f"{_csharp_type(field)} {pascal_identifier(field.name)}" for field in entity.fields
        )
        request_args = ", ".join(f"request.{pascal_identifier(field.name)}" for field in entity.fields)
        string_guards = [
            f"string.IsNullOrWhiteSpace(request.{pascal_identifier(field.name)})"
            for field in entity.fields
            if field.required and field.type == "string"
        ]
        guard_clause = ""
        if string_guards:
            guard = " || ".join(string_guards)
            guard_clause = clean(
                f"""
                if ({guard})
                {{
                    return Results.ValidationProblem(new Dictionary<string, string[]>
                    {{
                        ["request"] = ["All required string fields must be non-empty."]
                    }});
                }}
                """
            ).rstrip()
        store_name = f"{pascal_identifier(entity.plural)}Records"
        model_blocks.append(
            clean(
                f"""
                public sealed record {entity_class}Upsert(
                    {field_declarations}
                );

                public sealed record {entity_class}(
                    string Id,
                    {field_declarations}
                );
                """
            ).rstrip()
        )
        store_blocks.append(f"var {store_name} = new ConcurrentDictionary<string, {entity_type}>();")
        route_blocks.append(
            clean(
                f"""
                app.MapGet("/api/v1/{entity.plural}", () =>
                    Results.Ok({store_name}.Values.OrderBy(value => value.Id)));
                app.MapGet("/api/v1/{entity.plural}/{{id}}", (string id) =>
                    {store_name}.TryGetValue(id, out var value) ? Results.Ok(value) : Results.NotFound());
                app.MapPost("/api/v1/{entity.plural}", ({upsert_type} request) =>
                {{
                    {guard_clause}
                    var value = new {entity_type}(Guid.NewGuid().ToString(), {request_args});
                    {store_name}[value.Id] = value;
                    return Results.Created($"/api/v1/{entity.plural}/{{value.Id}}", value);
                }});
                app.MapPut("/api/v1/{entity.plural}/{{id}}", (string id, {upsert_type} request) =>
                {{
                    if (!{store_name}.ContainsKey(id))
                    {{
                        return Results.NotFound();
                    }}
                    {guard_clause}
                    var value = new {entity_type}(id, {request_args});
                    {store_name}[id] = value;
                    return Results.Ok(value);
                }});
                app.MapDelete("/api/v1/{entity.plural}/{{id}}", (string id) =>
                    {store_name}.TryRemove(id, out _) ? Results.NoContent() : Results.NotFound());
                """
            ).rstrip()
        )
        sample = csharp_sample(entity)
        test_blocks.append(
            clean(
                f"""
                [Fact]
                public async global::System.Threading.Tasks.Task {entity_class}FullCrudJourney()
                {{
                    using var payload = JsonContent.Create({sample});
                    var created = await _client.PostAsync("/api/v1/{entity.plural}", payload);
                    Assert.Equal(HttpStatusCode.Created, created.StatusCode);
                    var record = await created.Content.ReadFromJsonAsync<Dictionary<string, object>>();
                    var id = record!["id"].ToString();

                    var listing = await _client.GetAsync("/api/v1/{entity.plural}");
                    Assert.Equal(HttpStatusCode.OK, listing.StatusCode);
                    var fetched = await _client.GetAsync($"/api/v1/{entity.plural}/{{id}}");
                    Assert.Equal(HttpStatusCode.OK, fetched.StatusCode);

                    using var updatePayload = JsonContent.Create({sample});
                    var updated = await _client.PutAsync($"/api/v1/{entity.plural}/{{id}}", updatePayload);
                    Assert.Equal(HttpStatusCode.OK, updated.StatusCode);
                    var deleted = await _client.DeleteAsync($"/api/v1/{entity.plural}/{{id}}");
                    Assert.Equal(HttpStatusCode.NoContent, deleted.StatusCode);
                    Assert.Equal(HttpStatusCode.NotFound,
                        (await _client.GetAsync($"/api/v1/{entity.plural}/{{id}}")).StatusCode);
                }}
                """
            ).rstrip()
        )
    files: dict[str, str] = {
        ".gitignore": gitignore(),
        ".dockerignore": dockerignore(),
        ".env.example": env_example(request, port),
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
                <PackageVersion Include="Microsoft.AspNetCore.Mvc.Testing" Version="10.0.9" />
                <PackageVersion Include="Microsoft.NET.Test.Sdk" Version="18.8.1" />
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
            """
            <Project Sdk="Microsoft.NET.Sdk.Web">
              <PropertyGroup>
                <RootNamespace>Generated.Api</RootNamespace>
              </PropertyGroup>
            </Project>
            """
        ),
        f"src/{api_project}/Models.cs": clean(
            f"""
            namespace Generated.Api;

            {chr(10).join(model_blocks)}
            """
        ),
        f"src/{api_project}/Program.cs": clean(
            f"""
            using System.Collections.Concurrent;

            var builder = WebApplication.CreateBuilder(args);
            builder.Services.AddProblemDetails();
            var app = builder.Build();
            {chr(10).join(store_blocks)}

            app.UseExceptionHandler();
            app.MapGet("/health", () => Results.Ok(new {{ status = "UP", service = "{request.project_name}" }}));
            {chr(10).join(route_blocks)}

            app.Run();

            public partial class Program {{ }}
            """
        ),
        f"src/{api_project}/appsettings.json": clean(
            f"""
            {{
              "Application": {{
                "Name": "{request.project_name}",
                "Environment": "Development"
              }},
              "Logging": {{
                "LogLevel": {{
                  "Default": "Information",
                  "Microsoft.AspNetCore": "Warning"
                }}
              }},
              "AllowedHosts": "*"
            }}
            """
        ),
        f"src/{api_project}/Properties/launchSettings.json": clean(
            f"""
            {{
              "$schema": "http://json.schemastore.org/launchsettings.json",
              "profiles": {{
                "http": {{
                  "commandName": "Project",
                  "dotnetRunMessages": true,
                  "launchBrowser": false,
                  "applicationUrl": "http://localhost:{port}",
                  "environmentVariables": {{
                    "ASPNETCORE_ENVIRONMENT": "Development"
                  }}
                }}
              }}
            }}
            """
        ),
        f"tests/{test_project}/{test_project}.csproj": clean(
            f"""
            <Project Sdk="Microsoft.NET.Sdk">
              <PropertyGroup>
                <IsPackable>false</IsPackable>
                <IsTestProject>true</IsTestProject>
              </PropertyGroup>
              <ItemGroup>
                <PackageReference Include="Microsoft.AspNetCore.Mvc.Testing" />
                <PackageReference Include="Microsoft.NET.Test.Sdk" />
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
        f"tests/{test_project}/ApiTests.cs": clean(
            f"""
            using System.Net;
            using System.Net.Http.Json;
            using Microsoft.AspNetCore.Mvc.Testing;
            using Xunit;

            namespace Generated.Api.Tests;

            public sealed class ApiTests : IClassFixture<WebApplicationFactory<Program>>
            {{
                private readonly HttpClient _client;

                public ApiTests(WebApplicationFactory<Program> factory)
                {{
                    _client = factory.CreateClient();
                }}

                [Fact]
                public async global::System.Threading.Tasks.Task HealthJourney()
                {{
                    var health = await _client.GetAsync("/health");
                    Assert.Equal(HttpStatusCode.OK, health.StatusCode);
                }}

                {chr(10).join(test_blocks)}
            }}
            """
        ),
        "openapi.yaml": openapi_yaml(request, server_port=port),
        "Dockerfile": clean(
            f"""
            FROM {DOTNET_SDK_IMAGE} AS build
            WORKDIR /workspace
            COPY . .
            RUN dotnet publish src/{api_project}/{api_project}.csproj -c Release -o /out --no-self-contained

            FROM {DOTNET_ASPNET_IMAGE}
            RUN groupadd --system app && useradd --system --gid app --uid 10001 app
            WORKDIR /app
            COPY --from=build /out .
            USER 10001:10001
            ENV ASPNETCORE_URLS=http://+:{port}
            EXPOSE {port}
            ENTRYPOINT ["dotnet", "{api_project}.dll"]
            """
        ),
        "deploy/kubernetes.yaml": kubernetes_yaml(request, language="csharp", port=port),
        ".github/workflows/ci.yml": clean(
            f"""
            name: dotnet-ci
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
                  - uses: actions/setup-dotnet@67a3573c9a986a3f9c594539f4ab511d57bb3ce9 # v4
                    with:
                      dotnet-version: '10.0.x'
                  - run: dotnet restore {project_class}.slnx --locked-mode
                  - run: dotnet test {project_class}.slnx --no-restore -c Release
            """
        ),
        "Makefile": clean(
            f"""
            DOTNET ?= dotnet
            .PHONY: restore test run publish
            restore:
            \t$(DOTNET) restore {project_class}.slnx --locked-mode
            test:
            \t$(DOTNET) test {project_class}.slnx
            run:
            \tASPNETCORE_URLS=http://localhost:{port} $(DOTNET) run --project src/{api_project}/{api_project}.csproj
            publish:
            \t$(DOTNET) publish src/{api_project}/{api_project}.csproj -c Release
            """
        ),
        "README.md": target_readme(
            request,
            language="C# / .NET 10",
            framework="ASP.NET Core 10.0",
            port=port,
            commands=(
                f"dotnet restore {project_class}.slnx --locked-mode\n"
                f"dotnet test {project_class}.slnx\n"
                f"ASPNETCORE_URLS=http://localhost:{port} dotnet run --project src/{api_project}/{api_project}.csproj"
            ),
        ),
    }
    return files
