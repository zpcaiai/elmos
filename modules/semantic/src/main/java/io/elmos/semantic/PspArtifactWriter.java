package io.elmos.semantic;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.github.luben.zstd.ZstdOutputStream;

import java.io.BufferedOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.util.*;

import static io.elmos.semantic.PspModels.*;

public final class PspArtifactWriter {
    private static final Map<String, String> ARTIFACTS = Map.ofEntries(
            Map.entry("file", "files.jsonl.zst"), Map.entry("token", "syntax-nodes.jsonl.zst"), Map.entry("comment", "syntax-nodes.jsonl.zst"),
            Map.entry("syntax-node", "syntax-nodes.jsonl.zst"), Map.entry("scope", "scopes.jsonl.zst"), Map.entry("symbol", "symbols.jsonl.zst"),
            Map.entry("type", "types.jsonl.zst"), Map.entry("reference", "references.jsonl.zst"), Map.entry("inheritance-edge", "inheritance-edges.jsonl.zst"),
            Map.entry("call-site", "call-sites.jsonl.zst"), Map.entry("call-edge", "call-edges.jsonl.zst"), Map.entry("control-flow", "control-flow.jsonl.zst"),
            Map.entry("source-map", "source-maps.jsonl.zst"), Map.entry("diagnostic", "diagnostics.jsonl.zst"), Map.entry("external-dependency", "external-dependencies.jsonl.zst"));
    private final ObjectMapper json = new ObjectMapper().findAndRegisterModules().enable(SerializationFeature.INDENT_OUTPUT).enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);
    private final ObjectMapper jsonl = new ObjectMapper().findAndRegisterModules().enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);

    public void write(Path requestedWorkspace, SemanticDataset dataset, ConformanceReport report) {
        Path workspace = secureWorkspace(requestedWorkspace), semantic = workspace.resolve("semantic"), reports = workspace.resolve("reports");
        try {
            Files.createDirectories(semantic.resolve("extensions")); Files.createDirectories(semantic.resolve("indexes")); Files.createDirectories(reports);
            for (String language : List.of("java", "python", "csharp", "typescript", "javascript")) Files.createDirectories(workspace.resolve("logs").resolve(language + "-adapter"));
            writeJson(semantic.resolve("semantic-run-manifest.json"), dataset.manifest());
            writeJson(semantic.resolve("protocol-version.json"), Map.of("protocolVersion", PROTOCOL_VERSION, "idAlgorithmVersion", 1, "sourcePositionEncoding", "UTF-8-bytes", "columns", "zero-based"));
            Map<String, List<EntityEnvelope>> grouped = new TreeMap<>(); for (EntityEnvelope entity : dataset.entities()) grouped.computeIfAbsent(ARTIFACTS.getOrDefault(entity.entityKind(), "metrics.jsonl.zst"), ignored -> new ArrayList<>()).add(entity);
            for (String artifact : new TreeSet<>(ARTIFACTS.values())) writeJsonlZstd(semantic.resolve(artifact), grouped.getOrDefault(artifact, List.of()));
            writeJson(semantic.resolve("metrics.json"), dataset.manifest().metrics());
            for (String language : List.of("java", "python", "csharp", "typescript", "javascript"))
                writeJsonlZstd(semantic.resolve("extensions").resolve(language + ".jsonl.zst"), dataset.entities().stream().filter(entity -> entity.language().equals(language)).toList());
            writeIndex(semantic.resolve("indexes/semantic-index.sqlite"), dataset.entities());
            writeJson(reports.resolve("semantic-coverage-report.json"), report.coverage());
            writeJson(reports.resolve("unresolved-symbol-report.json"), diagnostics(dataset, Set.of("unresolved-symbol", "binding-failure", "missing-dependency", "missing-type-stub", "classpath-incomplete")));
            writeJson(reports.resolve("dynamic-feature-report.json"), diagnostics(dataset, Set.of("dynamic-call", "reflection", "runtime-code-generation", "framework-managed")));
            writeJson(reports.resolve("call-graph-coverage-report.json"), Map.of("exact", report.coverage().exactCallResolutionRate(), "candidate", report.coverage().candidateCallResolutionRate(), "dynamic", report.coverage().dynamicCallRate(), "unresolved", report.coverage().unresolvedCallRate()));
            writeJson(reports.resolve("semantic-conformance-report.json"), report);
        } catch (IOException | java.sql.SQLException error) { throw new IllegalStateException("PSP_ARTIFACT_WRITE_FAILED", error); }
    }

    private List<DiagnosticPayload> diagnostics(SemanticDataset dataset, Set<String> categories) { return dataset.entities().stream().map(EntityEnvelope::payload).filter(DiagnosticPayload.class::isInstance).map(DiagnosticPayload.class::cast).filter(value -> categories.contains(value.category())).toList(); }
    private void writeJson(Path target, Object value) throws IOException { atomic(target, json.writeValueAsBytes(value)); }
    private void writeJsonlZstd(Path target, List<EntityEnvelope> values) throws IOException {
        Path temporary = Files.createTempFile(target.getParent(), target.getFileName().toString(), ".tmp");
        try (var output = new ZstdOutputStream(new BufferedOutputStream(Files.newOutputStream(temporary)))) {
            for (EntityEnvelope value : values.stream().sorted(Comparator.comparing(EntityEnvelope::entityId)).toList()) { output.write(jsonl.writeValueAsBytes(value)); output.write('\n'); }
        }
        move(temporary, target);
    }
    private static void atomic(Path target, byte[] bytes) throws IOException { Path temporary = Files.createTempFile(target.getParent(), target.getFileName().toString(), ".tmp"); try { Files.write(temporary, bytes); move(temporary, target); } finally { Files.deleteIfExists(temporary); } }
    private static void move(Path temporary, Path target) throws IOException { try { Files.move(temporary, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING); } finally { Files.deleteIfExists(temporary); } }

    private void writeIndex(Path target, List<EntityEnvelope> entities) throws java.sql.SQLException, IOException {
        Path temporary = Files.createTempFile(target.getParent(), "semantic-index", ".sqlite");
        try (Connection connection = DriverManager.getConnection("jdbc:sqlite:" + temporary.toAbsolutePath())) {
            connection.setAutoCommit(false);
            connection.createStatement().execute("create table entities(entity_id text primary key, entity_kind text not null, project_id text not null, language text not null, artifact text not null)");
            connection.createStatement().execute("create table relations(source_id text not null, target_id text not null, relation_kind text not null, evidence_entity_id text not null)");
            connection.createStatement().execute("create table source_ranges(entity_id text not null, file_id text not null, start_byte integer not null, end_byte integer not null)");
            try (PreparedStatement entityInsert = connection.prepareStatement("insert into entities values(?,?,?,?,?)"); PreparedStatement relationInsert = connection.prepareStatement("insert into relations values(?,?,?,?)"); PreparedStatement rangeInsert = connection.prepareStatement("insert into source_ranges values(?,?,?,?)")) {
                for (EntityEnvelope entity : entities.stream().sorted(Comparator.comparing(EntityEnvelope::entityId)).toList()) {
                    entityInsert.setString(1, entity.entityId()); entityInsert.setString(2, entity.entityKind()); entityInsert.setString(3, entity.projectId()); entityInsert.setString(4, entity.language()); entityInsert.setString(5, ARTIFACTS.getOrDefault(entity.entityKind(), "metrics.jsonl.zst")); entityInsert.addBatch();
                    SourceRange range = range(entity.payload()); if (range != null) { rangeInsert.setString(1, entity.entityId()); rangeInsert.setString(2, range.fileId()); rangeInsert.setLong(3, range.startByte()); rangeInsert.setLong(4, range.endByte()); rangeInsert.addBatch(); }
                    relation(entity, relationInsert);
                }
                entityInsert.executeBatch(); rangeInsert.executeBatch(); relationInsert.executeBatch();
            }
            connection.commit();
        }
        move(temporary, target);
    }
    private static void relation(EntityEnvelope entity, PreparedStatement insert) throws java.sql.SQLException {
        Object payload = entity.payload(); String source = null, target = null, kind = entity.entityKind();
        if (payload instanceof ReferencePayload value) { source = value.sourceSymbolId(); target = value.targetSymbolId(); kind = value.kind(); }
        else if (payload instanceof RelationPayload value) { source = value.sourceSymbolId(); target = value.targetSymbolId(); kind = value.kind(); }
        else if (payload instanceof CallEdgePayload value) { source = value.callerSymbolId(); target = value.targetSymbolId(); kind = "CALLS"; }
        if (source != null && target != null) { insert.setString(1, source); insert.setString(2, target); insert.setString(3, kind); insert.setString(4, entity.entityId()); insert.addBatch(); }
    }
    private static SourceRange range(Object payload) { if (payload instanceof TokenPayload value) return value.sourceRange(); if (payload instanceof CommentPayload value) return value.sourceRange(); if (payload instanceof SyntaxNodePayload value) return value.sourceRange(); if (payload instanceof ScopePayload value) return value.sourceRange(); if (payload instanceof ReferencePayload value) return value.sourceRange(); if (payload instanceof RelationPayload value) return value.sourceRange(); if (payload instanceof CallSitePayload value) return value.sourceRange(); if (payload instanceof SourceMapPayload value) return value.sourceRange(); if (payload instanceof DiagnosticPayload value) return value.sourceRange(); return null; }
    private static Path secureWorkspace(Path requested) { Objects.requireNonNull(requested); Path absolute = requested.toAbsolutePath().normalize(); try { if (Files.exists(absolute, LinkOption.NOFOLLOW_LINKS) && (Files.isSymbolicLink(absolute) || !Files.isDirectory(absolute, LinkOption.NOFOLLOW_LINKS))) throw new SecurityException("workspace must be a real directory"); Files.createDirectories(absolute); return absolute.toRealPath(LinkOption.NOFOLLOW_LINKS); } catch (IOException error) { throw new IllegalArgumentException("WORKSPACE_UNAVAILABLE", error); } }
}
