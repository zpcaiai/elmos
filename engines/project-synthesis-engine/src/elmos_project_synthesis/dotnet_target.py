from __future__ import annotations

import json

from .models import FieldSpec, SynthesisRequest
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
    project_class = request.project_class
    entity_class = request.entity_class
    api_project = f"{project_class}.Api"
    test_project = f"{project_class}.Api.Tests"
    field_declarations = ",\n    ".join(
        f"{_csharp_type(field)} {pascal_identifier(field.name)}" for field in request.entity.fields
    )
    request_args = ", ".join(f"request.{pascal_identifier(field.name)}" for field in request.entity.fields)
    sample_values = sample_payload(request)
    csharp_values: list[str] = []
    for field in request.entity.fields:
        value = sample_values[field.name]
        if field.type == "string":
            rendered = json.dumps(value, ensure_ascii=False)
        elif field.type in {"integer", "number"}:
            rendered = str(value)
        elif field.type == "boolean":
            rendered = str(value).lower()
        else:
            rendered = f'DateTimeOffset.Parse("{value}")'
        csharp_values.append(f"{pascal_identifier(field.name)} = {rendered}")
    sample = "new { " + ", ".join(csharp_values) + " }"
    string_guards = [
        f"string.IsNullOrWhiteSpace(request.{pascal_identifier(field.name)})"
        for field in request.entity.fields
        if field.required and field.type == "string"
    ]
    guard = " || ".join(string_guards) or "false"
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

            public sealed record {entity_class}Create(
                {field_declarations}
            );

            public sealed record {entity_class}(
                string Id,
                {field_declarations}
            );
            """
        ),
        f"src/{api_project}/Program.cs": clean(
            f"""
            using System.Collections.Concurrent;
            using Generated.Api;

            var builder = WebApplication.CreateBuilder(args);
            builder.Services.AddProblemDetails();
            var app = builder.Build();
            var records = new ConcurrentDictionary<string, {entity_class}>();

            app.UseExceptionHandler();
            app.MapGet("/health", () => Results.Ok(new {{ status = "UP", service = "{request.project_name}" }}));
            app.MapGet("/api/v1/{request.entity.plural}", () => Results.Ok(records.Values.OrderBy(value => value.Id)));
            app.MapGet("/api/v1/{request.entity.plural}/{{id}}", (string id) =>
                records.TryGetValue(id, out var value) ? Results.Ok(value) : Results.NotFound());
            app.MapPost("/api/v1/{request.entity.plural}", ({entity_class}Create request) =>
            {{
                if ({guard})
                {{
                    return Results.ValidationProblem(new Dictionary<string, string[]>
                    {{
                        ["request"] = ["All required string fields must be non-empty."]
                    }});
                }}
                var value = new {entity_class}(Guid.NewGuid().ToString(), {request_args});
                records[value.Id] = value;
                return Results.Created($"/api/v1/{request.entity.plural}/{{value.Id}}", value);
            }});

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
                public async Task RequirementTracedCrudAndHealthJourney()
                {{
                    var health = await _client.GetAsync("/health");
                    Assert.Equal(HttpStatusCode.OK, health.StatusCode);

                    using var payload = JsonContent.Create({sample});
                    var created = await _client.PostAsync("/api/v1/{request.entity.plural}", payload);
                    Assert.Equal(HttpStatusCode.Created, created.StatusCode);

                    var listing = await _client.GetAsync("/api/v1/{request.entity.plural}");
                    Assert.Equal(HttpStatusCode.OK, listing.StatusCode);
                }}
            }}
            """
        ),
        "openapi.yaml": openapi_yaml(request, server_port=port),
        "Dockerfile": clean(
            f"""
            FROM mcr.microsoft.com/dotnet/sdk:10.0.301 AS build
            WORKDIR /workspace
            COPY . .
            RUN dotnet publish src/{api_project}/{api_project}.csproj -c Release -o /out --no-self-contained

            FROM mcr.microsoft.com/dotnet/aspnet:10.0.9
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
                  - uses: actions/checkout@v4
                  - uses: actions/setup-dotnet@v4
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
            \t$(DOTNET) restore {project_class}.slnx --use-lock-file
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
                f"dotnet restore {project_class}.slnx --use-lock-file\n"
                f"dotnet test {project_class}.slnx\n"
                f"ASPNETCORE_URLS=http://localhost:{port} dotnet run --project src/{api_project}/{api_project}.csproj"
            ),
        ),
    }
    return files
