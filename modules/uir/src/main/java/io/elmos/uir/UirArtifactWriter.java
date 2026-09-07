package io.elmos.uir;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.github.luben.zstd.ZstdOutputStream;

import java.io.BufferedOutputStream;
import java.io.IOException;
import java.nio.file.*;
import java.sql.DriverManager;
import java.util.*;

import static io.elmos.uir.UirModels.*;

public final class UirArtifactWriter {
    private static final Map<String,String> ARTIFACTS = Map.ofEntries(
            Map.entry("module","modules.jsonl.zst"), Map.entry("declaration","declarations.jsonl.zst"), Map.entry("type","types.jsonl.zst"),
            Map.entry("operation","operations.jsonl.zst"), Map.entry("region","regions.jsonl.zst"), Map.entry("block","blocks.jsonl.zst"),
            Map.entry("value","values.jsonl.zst"), Map.entry("cfg-edge","cfg-edges.jsonl.zst"), Map.entry("effect","effects.jsonl.zst"),
            Map.entry("effect-summary","effects.jsonl.zst"),
            Map.entry("exception-contract","exceptions.jsonl.zst"), Map.entry("async-contract","async-contracts.jsonl.zst"), Map.entry("alias","aliases.jsonl.zst"),
            Map.entry("obligation","obligations.jsonl.zst"), Map.entry("source-map","source-maps.jsonl.zst"), Map.entry("transformation","transformations.jsonl.zst"), Map.entry("diagnostic","diagnostics.jsonl.zst"));
    private final ObjectMapper json = new ObjectMapper().findAndRegisterModules().enable(SerializationFeature.INDENT_OUTPUT).enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);
    private final ObjectMapper jsonl = new ObjectMapper().findAndRegisterModules().enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);

    public void write(Path requestedWorkspace, Dataset dataset, ConformanceReport report, UirDialectRegistry registry) {
        Objects.requireNonNull(dataset); Objects.requireNonNull(report); Objects.requireNonNull(registry);
        Path workspace = secure(requestedWorkspace), uir = outputDirectory(workspace, "uir"), reports = outputDirectory(workspace, "reports");
        try {
            Path extensions = outputDirectory(uir, "extensions"), indexes = outputDirectory(uir, "indexes");
            Path logs = outputDirectory(workspace, "logs"); for (String log : List.of("lifting","canonicalization","analysis","validation")) outputDirectory(logs, log);
            writeJson(uir.resolve("uir-run-manifest.json"), dataset.manifest());
            writeJson(uir.resolve("protocol-version.json"), Map.of("protocolVersion", PROTOCOL_VERSION, "idAlgorithmVersion", 1, "contentHashAlgorithm", "canonical-json-sha256-v1", "unknownDialects", "opaque-forward"));
            writeJson(uir.resolve("dialect-registry.json"), registry.all());
            Map<String,List<Entity>> grouped = new TreeMap<>(); for (Entity entity : dataset.entities()) {
                String artifact = ARTIFACTS.get(entity.entityKind()); if (artifact == null) throw new IllegalArgumentException("UIR_ENTITY_KIND_UNSUPPORTED:" + entity.entityKind());
                grouped.computeIfAbsent(artifact, ignored -> new ArrayList<>()).add(entity);
            }
            for (String artifact : new TreeSet<>(ARTIFACTS.values())) writeZstd(uir.resolve(artifact), grouped.getOrDefault(artifact, List.of()));
            Map<String,String> moduleLanguages = new HashMap<>(); dataset.entities().stream().map(Entity::payload).filter(UirModels.Module.class::isInstance).map(UirModels.Module.class::cast).forEach(module -> moduleLanguages.put(module.moduleId(), module.sourceLanguage()));
            for (String language : List.of("java","python","csharp","javascript","typescript"))
                writeZstd(extensions.resolve(language + ".jsonl.zst"), dataset.entities().stream().filter(entity -> language.equals(moduleLanguages.get(entity.moduleId()))).toList());
            writeIndex(indexes.resolve("uir-index.sqlite"), dataset.entities());
            writeJson(reports.resolve("uir-coverage-report.json"), report.coverage()); writeJson(reports.resolve("uir-conformance-report.json"), report);
            writeJson(reports.resolve("effect-report.json"), dataset.entities().stream().filter(entity -> entity.payload() instanceof Effect || entity.payload() instanceof EffectSummary).map(Entity::payload).toList()); writeJson(reports.resolve("exception-report.json"), payloads(dataset, ExceptionContract.class));
            writeJson(reports.resolve("async-report.json"), payloads(dataset, AsyncContract.class)); writeJson(reports.resolve("mutability-report.json"), payloads(dataset, Alias.class));
            writeJson(reports.resolve("dynamic-risk-report.json"), dataset.entities().stream().filter(entity -> entity.payload() instanceof Operation operation && (operation.dialect().equals("uir.dynamic") || operation.dialect().startsWith("uir.lang."))).toList());
            writeJson(reports.resolve("semantic-obligation-report.json"), payloads(dataset, Obligation.class));
        } catch (SecurityException error) { throw error; }
        catch (Exception error) { throw new IllegalStateException("UIR_ARTIFACT_WRITE_FAILED", error); }
    }
    private <T> List<T> payloads(Dataset dataset, Class<T> type) { return dataset.entities().stream().map(Entity::payload).filter(type::isInstance).map(type::cast).toList(); }
    private void writeJson(Path path, Object value) throws IOException { atomic(path, json.writeValueAsBytes(value)); }
    private void writeZstd(Path path, List<Entity> entities) throws IOException { Path temp = Files.createTempFile(path.getParent(), path.getFileName().toString(), ".tmp"); try (var output = new ZstdOutputStream(new BufferedOutputStream(Files.newOutputStream(temp)))) { for (Entity entity : entities.stream().sorted(Comparator.comparing(Entity::entityId)).toList()) { output.write(jsonl.writeValueAsBytes(entity)); output.write('\n'); } } move(temp, path); }
    private void writeIndex(Path path, List<Entity> entities) throws Exception {
        Path temp = Files.createTempFile(path.getParent(), "uir-index", ".sqlite");
        try (var connection = DriverManager.getConnection("jdbc:sqlite:" + temp.toAbsolutePath())) {
            connection.setAutoCommit(false);
            connection.createStatement().execute("create table entities(entity_id text primary key, entity_kind text not null, module_id text not null, artifact text not null, content_hash text not null, generation integer not null, supersedes text, deleted integer not null)");
            connection.createStatement().execute("create table links(source_id text not null, target_id text not null, link_kind text not null)");
            connection.createStatement().execute("create index links_source on links(source_id,link_kind)");
            connection.createStatement().execute("create index links_target on links(target_id,link_kind)");
            try (var insert = connection.prepareStatement("insert into entities values(?,?,?,?,?,?,?,?)"); var link = connection.prepareStatement("insert into links values(?,?,?)")) {
                for (Entity entity : entities.stream().sorted(Comparator.comparing(Entity::entityId)).toList()) {
                    insert.setString(1, entity.entityId()); insert.setString(2, entity.entityKind()); insert.setString(3, entity.moduleId()); insert.setString(4, ARTIFACTS.get(entity.entityKind()));
                    insert.setString(5, entity.contentHash()); insert.setLong(6, entity.generation()); insert.setString(7, entity.supersedes()); insert.setInt(8, entity.deleted() ? 1 : 0); insert.addBatch();
                    indexLinks(link, entity);
                }
                insert.executeBatch(); link.executeBatch();
            }
            connection.commit();
        }
        move(temp,path);
    }
    private static void indexLinks(java.sql.PreparedStatement link, Entity entity) throws Exception {
        Object payload = entity.payload(); String source = entity.entityId();
        if (payload instanceof UirModels.Module value) value.declarationIds().forEach(target -> addLink(link, source, target, "CONTAINS"));
        else if (payload instanceof Declaration value) {
            addLink(link, source, value.typeId(), "HAS_TYPE"); addLink(link, source, value.bodyRegionId(), "HAS_BODY");
            value.sourceSymbolIds().forEach(target -> addLink(link, source, target, "LIFTED_FROM"));
        } else if (payload instanceof Operation value) {
            value.operands().forEach(target -> addLink(link, source, target, "USES")); value.results().forEach(result -> addLink(link, source, result.valueId(), "DEFINES"));
            value.effectIds().forEach(target -> addLink(link, source, target, "HAS_EFFECT")); value.sourceMapIds().forEach(target -> addLink(link, source, target, "HAS_SOURCE_MAP"));
            value.regionIds().forEach(target -> addLink(link, source, target, "OWNS_REGION"));
        } else if (payload instanceof Value value) {
            if (value.definition() != null) addLink(link, source, value.definition().operationId(), "DEFINED_BY"); value.uses().forEach(use -> addLink(link, source, use.operationId(), "USED_BY"));
        } else if (payload instanceof CfgEdge value) {
            addLink(link, source, value.fromBlockId(), "CFG_FROM"); addLink(link, source, value.toBlockId(), "CFG_TO");
        } else if (payload instanceof Effect value) addLink(link, source, value.operationId(), "APPLIES_TO");
        else if (payload instanceof EffectSummary value) {
            addLink(link, source, value.callableDeclarationId(), "SUMMARIZES_CALLABLE"); value.effectIds().forEach(target -> addLink(link, source, target, "SUMMARIZES_EFFECT"));
        }
        else if (payload instanceof Obligation value) {
            addLink(link, source, value.declarationId(), "SCOPES_DECLARATION"); addLink(link, source, value.operationId(), "SCOPES_OPERATION");
        } else if (payload instanceof SourceMap value) {
            value.pspEntityIds().forEach(target -> addLink(link, source, target, "MAPS_FROM_PSP")); value.uirEntityIds().forEach(target -> addLink(link, source, target, "MAPS_TO_UIR"));
        } else if (payload instanceof Transformation value) {
            value.inputEntityIds().forEach(target -> addLink(link, source, target, "TRANSFORMS_FROM")); value.outputEntityIds().forEach(target -> addLink(link, source, target, "TRANSFORMS_TO"));
        }
    }
    private static void addLink(java.sql.PreparedStatement link, String source, String target, String kind) {
        if (target == null) return; try { link.setString(1, source); link.setString(2, target); link.setString(3, kind); link.addBatch(); }
        catch (java.sql.SQLException error) { throw new IllegalStateException("UIR_INDEX_LINK_FAILED", error); }
    }
    private static void atomic(Path path, byte[] bytes) throws IOException { Path temp = Files.createTempFile(path.getParent(), path.getFileName().toString(), ".tmp"); try { Files.write(temp,bytes); move(temp,path); } finally { Files.deleteIfExists(temp); } }
    private static void move(Path temp, Path path) throws IOException { try { Files.move(temp,path,StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING); } finally { Files.deleteIfExists(temp); } }
    private static Path secure(Path requested) { try { Path path = requested.toAbsolutePath().normalize(); if (Files.exists(path,LinkOption.NOFOLLOW_LINKS) && Files.isSymbolicLink(path)) throw new SecurityException("UIR_WORKSPACE_SYMLINK"); Files.createDirectories(path); return path.toRealPath(LinkOption.NOFOLLOW_LINKS); } catch (IOException error) { throw new IllegalArgumentException("UIR_WORKSPACE_UNAVAILABLE", error); } }
    private static Path outputDirectory(Path workspace, String name) {
        Path output = workspace.resolve(name); if (Files.exists(output, LinkOption.NOFOLLOW_LINKS) && Files.isSymbolicLink(output)) throw new SecurityException("UIR_OUTPUT_SYMLINK:" + name);
        try { Files.createDirectories(output); return output.toRealPath(LinkOption.NOFOLLOW_LINKS); }
        catch (IOException error) { throw new IllegalArgumentException("UIR_OUTPUT_UNAVAILABLE:" + name, error); }
    }
}
