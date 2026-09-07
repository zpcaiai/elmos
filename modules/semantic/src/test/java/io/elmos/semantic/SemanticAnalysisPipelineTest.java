package io.elmos.semantic;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.github.luben.zstd.ZstdInputStream;
import io.elmos.intake.BaselineRunner;
import io.elmos.intake.IntakeModels.*;
import io.elmos.intake.RepositoryIntakeService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.DriverManager;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static io.elmos.semantic.PspModels.*;
import static org.junit.jupiter.api.Assertions.*;

class SemanticAnalysisPipelineTest {
    @TempDir Path root;
    private final Clock clock = Clock.fixed(Instant.parse("2026-07-20T16:00:00Z"), ZoneOffset.UTC);

    @Test void routesFourLanguagesPreservesUtf8RangesAndBlocksFallbackFromBatchThree() throws Exception {
        writePolyglotRepository();
        IntakeBundle intake = intake();
        SemanticAnalysisOrchestrator orchestrator = new SemanticAnalysisOrchestrator(List.of(
                new LosslessFallbackAdapter("java"), new LosslessFallbackAdapter("python"),
                new LosslessFallbackAdapter("csharp"), new LosslessFallbackAdapter("typescript")), clock);

        SemanticDataset first = orchestrator.analyze(root, intake, AnalysisProfile.full(), new ResourceBudget(2, 1024, 120), Map.of("mode", "offline"));
        SemanticDataset second = orchestrator.analyze(root, intake, AnalysisProfile.full(), new ResourceBudget(2, 1024, 120), Map.of("mode", "offline"));
        assertEquals(first.manifest().semanticRunId(), second.manifest().semanticRunId());
        assertEquals(first.entities().stream().map(EntityEnvelope::entityId).toList(), second.entities().stream().map(EntityEnvelope::entityId).toList());
        assertEquals(Set.of("java", "python", "csharp", "typescript"),
                Set.copyOf(first.entities().stream().filter(entity -> entity.entityKind().equals("file")).map(EntityEnvelope::language).toList()));
        assertEquals(4, first.entities().stream().filter(entity -> entity.payload() instanceof DiagnosticPayload diagnostic
                && diagnostic.nativeCode().equals("AUTHORITATIVE_PROVIDER_UNAVAILABLE") && diagnostic.blocking()).count());

        EntityEnvelope unicode = first.entities().stream().filter(entity -> entity.payload() instanceof TokenPayload token
                && token.textHash().equals(SemanticIds.hashText("中文"))).findFirst().orElseThrow();
        TokenPayload unicodeToken = (TokenPayload) unicode.payload();
        assertEquals("python", unicode.language(), "two CJK characters must occupy six UTF-8 bytes");
        assertEquals(6, unicodeToken.sourceRange().endByte() - unicodeToken.sourceRange().startByte());
        FilePayload python = first.entities().stream().map(EntityEnvelope::payload).filter(FilePayload.class::isInstance)
                .map(FilePayload.class::cast).filter(file -> file.language().equals("python")).findFirst().orElseThrow();
        assertEquals("CRLF", python.lineEnding());

        ConformanceReport report = new SemanticConformanceValidator().validate(first);
        assertEquals("blocked", report.status());
        assertTrue(report.modules().stream().noneMatch(ModuleGate::eligibleForBatch3));
        assertTrue(report.modules().stream().allMatch(module -> module.restrictions().contains("blocking-diagnostic")));
    }

    @Test void emitsCompressedProtocolArtifactsAndQueryableSqliteIndex() throws Exception {
        writePolyglotRepository();
        SemanticDataset dataset = new SemanticAnalysisOrchestrator(List.of(
                new LosslessFallbackAdapter("java"), new LosslessFallbackAdapter("python"),
                new LosslessFallbackAdapter("csharp"), new LosslessFallbackAdapter("typescript")), clock)
                .analyze(root, intake(), AnalysisProfile.full(), new ResourceBudget(2, 1024, 120), Map.of());
        ConformanceReport report = new SemanticConformanceValidator().validate(dataset);
        Path workspace = root.resolve("batch-2-workspace"); new PspArtifactWriter().write(workspace, dataset, report);

        for (String artifact : List.of("semantic-run-manifest.json", "protocol-version.json", "files.jsonl.zst", "syntax-nodes.jsonl.zst",
                "scopes.jsonl.zst", "symbols.jsonl.zst", "types.jsonl.zst", "references.jsonl.zst", "inheritance-edges.jsonl.zst",
                "call-sites.jsonl.zst", "call-edges.jsonl.zst", "control-flow.jsonl.zst", "source-maps.jsonl.zst", "diagnostics.jsonl.zst",
                "indexes/semantic-index.sqlite")) assertTrue(Files.isRegularFile(workspace.resolve("semantic").resolve(artifact)), artifact);
        for (String reportName : List.of("semantic-coverage-report.json", "unresolved-symbol-report.json", "dynamic-feature-report.json",
                "call-graph-coverage-report.json", "semantic-conformance-report.json"))
            assertTrue(Files.isRegularFile(workspace.resolve("reports").resolve(reportName)), reportName);

        try (var input = new ZstdInputStream(Files.newInputStream(workspace.resolve("semantic/files.jsonl.zst")));
             var lines = new BufferedReader(new InputStreamReader(input, StandardCharsets.UTF_8)).lines()) {
            List<String> jsonl = lines.toList(); assertEquals(4, jsonl.size());
            JsonNode first = new ObjectMapper().readTree(jsonl.getFirst()); assertEquals(PROTOCOL_VERSION, first.path("protocolVersion").asText());
        }
        try (var connection = DriverManager.getConnection("jdbc:sqlite:" + workspace.resolve("semantic/indexes/semantic-index.sqlite").toAbsolutePath());
             var statement = connection.createStatement(); var result = statement.executeQuery("select count(*) from entities")) {
            assertTrue(result.next()); assertEquals(dataset.entities().size(), result.getInt(1));
        }
    }

    @Test void rejectsChangedSnapshotAndInvalidProviderAndDetectsOutOfBoundsRanges() throws Exception {
        writePolyglotRepository(); IntakeBundle intake = intake();
        SemanticAnalysisOrchestrator orchestrator = new SemanticAnalysisOrchestrator(List.of(
                new LosslessFallbackAdapter("java"), new LosslessFallbackAdapter("python"),
                new LosslessFallbackAdapter("csharp"), new LosslessFallbackAdapter("typescript")), clock);
        write("python/src/app.py", "def changed():\n    pass\n");
        assertThrows(IllegalArgumentException.class, () -> orchestrator.analyze(root, intake, AnalysisProfile.full(), new ResourceBudget(1, 512, 30), Map.of()));

        AdapterDescriptor invalid = new AdapterDescriptor("bad", "1", "python", "tree-sitter", "1", true, true, "sha256:x");
        assertThrows(SecurityException.class, () -> new AuthoritySemanticAdapter(invalid, (descriptor, request) -> null));

        Provenance provenance = new Provenance("test", "1", "test", "1", "fixture", "full", "exact", 1, List.of(), Instant.EPOCH);
        String snapshot = "snap", run = "run", project = "project"; SourceRange invalidRange = new SourceRange("file:1", 0, 9, 1, 0, 1, 9);
        List<EntityEnvelope> entities = List.of(
                new EntityEnvelope(PROTOCOL_VERSION, "file", "file:1", snapshot, run, project, "java", new FilePayload("file:1", project, "A.java", "java", "sha256:x", 3, "UTF-8", "LF", "production-source", false, false, "test", false), provenance),
                new EntityEnvelope(PROTOCOL_VERSION, "syntax-node", "node:1", snapshot, run, project, "java", new SyntaxNodePayload("node:1", "file", null, invalidRange, false, List.of(), List.of(), Map.of()), provenance));
        SemanticRunManifest manifest = new SemanticRunManifest(run, snapshot, "completed", List.of(), List.of(project), List.of(),
                new CoverageMetrics(0, 0, 0, 0, 0, 0, 0, 0), List.of(), "sha256:x", Instant.EPOCH);
        ConformanceReport report = new SemanticConformanceValidator().validate(new SemanticDataset(manifest, entities));
        assertEquals("failed", report.status()); assertTrue(report.violations().stream().anyMatch(value -> value.startsWith("SOURCE_RANGE_OUT_OF_BOUNDS")));
    }

    private IntakeBundle intake() {
        BaselineRunner passed = (snapshot, build, policy) -> new BaselineReport("1.0", snapshot.snapshotId(), "image@sha256:" + "c".repeat(64),
                Status.PASSED, Status.PASSED, Status.PASSED, 4, 4, 0, 0, .80, List.of(), List.of(), List.of());
        IntakeRequest request = new IntakeRequest(SourceType.UPLOAD, null, null, null, "semantic-fixture", "java", "spring-boot", ScanLimits.defaults());
        return new RepositoryIntakeService(clock, passed).analyze(root, request);
    }

    private void writePolyglotRepository() throws Exception {
        write("pom.xml", "<project><modelVersion>4.0.0</modelVersion><groupId>x</groupId><artifactId>j</artifactId><version>1</version></project>");
        write("src/main/java/x/App.java", "package x; /** docs */ class App {}\n");
        write("python/pyproject.toml", "[project]\nname='p'\nversion='1'\n");
        write("python/src/app.py", "# 注释\r\ndef 中文():\r\n    return 1\r\n");
        write("dotnet/App.csproj", "<Project Sdk=\"Microsoft.NET.Sdk\"><PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup></Project>");
        write("dotnet/Program.cs", "record App(int Value);\n");
        write("web/package.json", "{\"name\":\"w\",\"devDependencies\":{\"typescript\":\"5.9.2\"}}");
        write("web/tsconfig.json", "{\"compilerOptions\":{\"strict\":true}}");
        write("web/src/main.ts", "export interface App { value: number }\n");
    }

    private void write(String relative, String content) throws Exception {
        Path target = root.resolve(relative); Files.createDirectories(target.getParent()); Files.writeString(target, content, StandardCharsets.UTF_8);
    }
}
