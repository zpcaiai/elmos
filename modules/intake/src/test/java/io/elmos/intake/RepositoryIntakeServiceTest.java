package io.elmos.intake;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;

import static io.elmos.intake.IntakeModels.*;
import static org.junit.jupiter.api.Assertions.*;

class RepositoryIntakeServiceTest {
    @TempDir Path root;
    private final Clock clock = Clock.fixed(Instant.parse("2026-07-20T12:00:00Z"), ZoneOffset.UTC);

    @Test void inventoriesFourLanguagesWithFormatAwareBuildParsingAndNoTranslation() throws Exception {
        write("pom.xml", """
                <project><modelVersion>4.0.0</modelVersion><groupId>sample</groupId><artifactId>java-app</artifactId><version>1</version>
                <properties><java.version>17</java.version><spring.version>3.5.3</spring.version></properties>
                <dependencies><dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-web</artifactId><version>${spring.version}</version></dependency></dependencies></project>
                """);
        write("src/main/java/sample/App.java", "package sample; class App {}\n");
        write("src/test/java/sample/AppTest.java", "package sample; class AppTest {}\n");
        write("python/pyproject.toml", """
                [project]
                name = "py-app"
                requires-python = ">=3.12"
                dependencies = ["fastapi>=0.115", "pydantic>=2"]
                [project.optional-dependencies]
                test = ["pytest>=8"]
                """);
        write("python/src/py_app/main.py", "from fastapi import FastAPI\napp = FastAPI()\n");
        write("dotnet/App.csproj", """
                <Project Sdk="Microsoft.NET.Sdk.Web"><PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup>
                <ItemGroup><PackageReference Include="Microsoft.AspNetCore.OpenApi" /></ItemGroup></Project>
                """);
        write("dotnet/Directory.Packages.props", "<Project><ItemGroup><PackageVersion Include=\"Microsoft.AspNetCore.OpenApi\" Version=\"8.0.7\" /></ItemGroup></Project>");
        write("dotnet/Program.cs", "var app = WebApplication.CreateBuilder(args).Build();\n");
        write("web/package.json", """
                {"name":"web-app","scripts":{"build":"tsc --noEmit","test":"vitest run"},"dependencies":{"@nestjs/core":"11.1.0","express":"5.1.0"},"devDependencies":{"typescript":"5.8.3"}}
                """);
        write("web/tsconfig.json", "{}"); write("web/src/main.ts", "export const ok: boolean = true;\n");
        write(".env", "TOP_SECRET=must-never-appear-in-manifests\n");
        write("target/generated/Generated.java", "// generated code\nclass Generated {}\n");

        IntakeBundle bundle = service(BaselineRunner.disabled("approved sandbox runner is not configured")).analyze(root, uploadRequest());
        assertEquals(4, bundle.fingerprint().languages().size());
        assertEquals(java.util.Set.of(Language.JAVA, Language.TYPESCRIPT, Language.PYTHON, Language.CSHARP),
                java.util.Set.copyOf(bundle.fingerprint().languages().stream().map(LanguageFingerprint::language).toList()));
        assertTrue(bundle.fingerprint().frameworks().stream().anyMatch(value -> value.name().equals("spring-boot")));
        assertTrue(bundle.fingerprint().frameworks().stream().anyMatch(value -> value.name().equals("fastapi")), bundle.buildModel().toString());
        assertTrue(bundle.fingerprint().frameworks().stream().anyMatch(value -> value.name().equals("aspnet-core")));
        assertTrue(bundle.fingerprint().frameworks().stream().anyMatch(value -> value.name().equals("nestjs")));
        assertEquals(4, bundle.buildModel().projects().size());
        assertTrue(bundle.buildModel().projects().stream().flatMap(value -> value.dependencies().stream()).anyMatch(value -> value.name().equals("Microsoft.AspNetCore.OpenApi") && value.version().equals("8.0.7")));
        assertTrue(bundle.buildModel().projects().stream().flatMap(value -> value.dependencies().stream()).anyMatch(value -> value.scope().equals("extra:test")));
        assertTrue(bundle.inventory().files().stream().filter(value -> value.path().equals(".env")).allMatch(FileEntry::excludedFromModel));
        assertTrue(bundle.inventory().files().stream().filter(value -> value.path().contains("Generated.java")).allMatch(FileEntry::generated));
        assertEquals(Status.BLOCKED, bundle.migrationManifest().gateStatus());
        assertTrue(bundle.dependencyGraph().unresolved().stream().anyMatch(value -> value.contains("Batch 2")));
    }

    @Test void snapshotIdentityIsDeterministicAndBoundToSourceIdentity() throws Exception {
        write("package.json", "{\"name\":\"x\",\"dependencies\":{}}"); write("src/a.js", "export default 1;\n");
        IntakeBundle first = service(BaselineRunner.disabled("not run")).analyze(root, uploadRequest());
        IntakeBundle second = service(BaselineRunner.disabled("not run")).analyze(root, uploadRequest());
        assertEquals(first.snapshot().snapshotId(), second.snapshot().snapshotId());
        assertEquals(first.snapshot().integrityHash(), second.snapshot().integrityHash());
        Files.writeString(root.resolve("src/a.js"), "export default 2;\n");
        IntakeBundle changed = service(BaselineRunner.disabled("not run")).analyze(root, uploadRequest());
        assertNotEquals(first.snapshot().snapshotId(), changed.snapshot().snapshotId());
    }

    @Test void requiresResolvedCredentialFreeGitProvenanceAndRejectsSymlinks() throws Exception {
        write("pom.xml", "<project><modelVersion>4.0.0</modelVersion><artifactId>x</artifactId></project>");
        IntakeRequest credentialRemote = new IntakeRequest(SourceType.GIT, "https://token@example.com/org/repo.git", "main", "a".repeat(40), null, "csharp", "aspnet-core", ScanLimits.defaults());
        assertThrows(IllegalArgumentException.class, () -> service(BaselineRunner.disabled("not run")).analyze(root, credentialRemote));
        IntakeRequest floatingRef = new IntakeRequest(SourceType.GIT, "https://example.com/org/repo.git", "main", null, null, "csharp", "aspnet-core", ScanLimits.defaults());
        assertThrows(IllegalArgumentException.class, () -> service(BaselineRunner.disabled("not run")).analyze(root, floatingRef));
        IntakeRequest ssh = new IntakeRequest(SourceType.GIT, "ssh://git@example.com/org/repo.git", "main", "a".repeat(40), null, "csharp", "aspnet-core", ScanLimits.defaults());
        assertEquals("ssh://example.com/org/repo.git", service(BaselineRunner.disabled("not run")).analyze(root, ssh).snapshot().repository().remote());
        Path outside = Files.createTempFile("elmos-intake", ".txt"); Files.createSymbolicLink(root.resolve("escape"), outside);
        try { assertThrows(SecurityException.class, () -> service(BaselineRunner.disabled("not run")).analyze(root, uploadRequest())); }
        finally { Files.deleteIfExists(outside); }
    }

    @Test void writesTheFrozenBatchOneWorkspaceAndPassesOnlyWithRecordedBaseline() throws Exception {
        write("package.json", "{\"name\":\"x\",\"scripts\":{\"test\":\"node --test\"},\"dependencies\":{\"express\":\"5.1.0\"}}");
        write("src/a.js", "export default 1;\n");
        BaselineRunner passed = (snapshot, build, policy) -> new BaselineReport("1.0", snapshot.snapshotId(), "image@sha256:" + "b".repeat(64),
                Status.PASSED, Status.PASSED, Status.PASSED, 2, 2, 0, 0, 0.80,
                List.of(new BaselineStep("test", Status.PASSED, 0, 20, "artifact:stdout", "artifact:stderr", null, List.of())), List.of(), List.of());
        IntakeBundle bundle = service(passed).analyze(root, uploadRequest());
        assertEquals(Status.PASSED, bundle.migrationManifest().gateStatus());
        assertTrue(bundle.migrationManifest().readiness().total() > 50);
        Path workspace = root.resolve("migration-workspace"); new MigrationWorkspaceWriter().write(workspace, bundle);
        for (String name : List.of("repository-snapshot.json", "project-fingerprint.json", "build-model.json", "source-inventory.json",
                "dependency-graph.json", "baseline-report.json", "sandbox-policy.yaml", "migration-manifest.yaml"))
            assertTrue(Files.isRegularFile(workspace.resolve("manifests").resolve(name)), name);
        String all = Files.readString(workspace.resolve("manifests/source-inventory.json"));
        assertFalse(all.contains("export default 1"));
        JsonNode snapshot = new ObjectMapper().readTree(workspace.resolve("manifests/repository-snapshot.json").toFile());
        assertEquals(bundle.snapshot().snapshotId(), snapshot.path("snapshotId").asText());
    }

    @Test void rejectsXxeWithoutLeakingHostFile() throws Exception {
        write("pom.xml", "<!DOCTYPE foo [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]><project><artifactId>&xxe;</artifactId></project>");
        IntakeBundle bundle = service(BaselineRunner.disabled("not run")).analyze(root, uploadRequest());
        assertTrue(bundle.buildModel().unresolved().stream().anyMatch(value -> value.contains("XML_BUILD_MANIFEST_PARSE_FAILED")));
        assertTrue(bundle.buildModel().projects().isEmpty());
    }

    @Test void modelsRequirementsAndLeavesExecutableBuildDslUnresolved() throws Exception {
        write("python/requirements.txt", "fastapi==0.115.0\n-r private.txt\ngit+https://example.invalid/project.git\n");
        write("python/app.py", "print('safe')\n");
        write("java/build.gradle.kts", "plugins { java }\ndependencies { implementation(\"x:y:1\") }\n");
        write("java/src/main/java/x/App.java", "package x; class App {}\n");
        IntakeBundle bundle = service(BaselineRunner.disabled("not run")).analyze(root, uploadRequest());
        assertTrue(bundle.buildModel().projects().stream().anyMatch(value -> value.buildTool().equals("pip") && value.dependencies().stream().anyMatch(dependency -> dependency.name().equals("fastapi"))));
        BuildProject gradle = bundle.buildModel().projects().stream().filter(value -> value.buildTool().equals("gradle")).findFirst().orElseThrow();
        assertTrue(gradle.dependencies().isEmpty());
        assertTrue(gradle.unresolved().stream().anyMatch(value -> value.contains("not evaluated")));
        assertTrue(bundle.buildModel().projects().stream().filter(value -> value.buildTool().equals("pip")).flatMap(value -> value.unresolved().stream()).anyMatch(value -> value.startsWith("non-registry-requirement:")));
    }

    private RepositoryIntakeService service(BaselineRunner runner) { return new RepositoryIntakeService(clock, runner); }
    private IntakeRequest uploadRequest() { return new IntakeRequest(SourceType.UPLOAD, null, null, null, "upload-1", "csharp", "aspnet-core", ScanLimits.defaults()); }
    private void write(String relative, String content) throws Exception { Path file = root.resolve(relative); Files.createDirectories(file.getParent()); Files.writeString(file, content); }
}
