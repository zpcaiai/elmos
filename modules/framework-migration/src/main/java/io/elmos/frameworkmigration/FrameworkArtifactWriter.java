package io.elmos.frameworkmigration;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.github.luben.zstd.ZstdOutputStream;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.file.*;
import java.util.LinkedHashMap;
import java.util.Map;

import static io.elmos.frameworkmigration.FrameworkMigrationModels.RunResult;

/** Writes Batch 7 evidence only. Target-repository mutation belongs to the approved native backend. */
public final class FrameworkArtifactWriter {
    private final ObjectMapper mapper = new ObjectMapper().registerModule(new JavaTimeModule())
            .enable(SerializationFeature.INDENT_OUTPUT)
            .enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);

    public Map<String,Path> write(Path migrationWorkspace, RunResult result) throws IOException {
        Path root = secureRoot(migrationWorkspace);
        Map<String,Object> json = new LinkedHashMap<>();
        json.put("framework/framework-fingerprint.json", result.fingerprint());
        json.put("framework/afsm-version.json", Map.of("afsmVersion", "1.0"));
        json.put("framework/framework-migration-manifest.json", result.manifest());
        json.put("recipes/plans/framework-recipe-plans.json", result.recipePlans());
        json.put("mappings/afsm-target-emissions.json", result.emissions());
        json.put("reports/framework-semantic-differences.json", result.differences());
        json.put("reports/framework-obligations.json", result.obligations());
        json.put("reports/framework-startup-validation.json", result.validation());
        json.put("reports/batch-7-conformance-report.json", result.conformance());
        Map<String,Path> written = new LinkedHashMap<>();
        for (Map.Entry<String,Object> entry : json.entrySet()) {
            Path target = secureTarget(root, entry.getKey());
            atomicWrite(target, mapper.writeValueAsBytes(entry.getValue()));
            written.put(entry.getKey(), target);
        }
        String entityPath = "framework/entities.jsonl.zst";
        Path entityTarget = secureTarget(root, entityPath);
        ByteArrayOutputStream compressed = new ByteArrayOutputStream();
        try (ZstdOutputStream output = new ZstdOutputStream(compressed)) {
            for (Object entity : result.lift().entities()) {
                output.write(mapper.writeValueAsBytes(entity)); output.write('\n');
            }
        }
        atomicWrite(entityTarget, compressed.toByteArray()); written.put(entityPath, entityTarget);
        return Map.copyOf(written);
    }

    private Path secureRoot(Path requested) throws IOException {
        Path root = requested.toAbsolutePath().normalize();
        if (Files.exists(root, LinkOption.NOFOLLOW_LINKS) && Files.isSymbolicLink(root))
            throw new SecurityException("FRAMEWORK_WORKSPACE_SYMLINK");
        Files.createDirectories(root);
        if (Files.isSymbolicLink(root)) throw new SecurityException("FRAMEWORK_WORKSPACE_SYMLINK");
        return root.toRealPath(LinkOption.NOFOLLOW_LINKS);
    }

    private Path secureTarget(Path root, String relative) throws IOException {
        Path target = root.resolve(relative).normalize();
        if (!target.startsWith(root)) throw new SecurityException("FRAMEWORK_ARTIFACT_PATH_ESCAPE");
        Path current = root;
        Path relativeParent = root.relativize(target.getParent());
        for (Path part : relativeParent) {
            current = current.resolve(part);
            if (Files.exists(current, LinkOption.NOFOLLOW_LINKS) && Files.isSymbolicLink(current))
                throw new SecurityException("FRAMEWORK_ARTIFACT_PARENT_SYMLINK:" + current);
            if (!Files.exists(current, LinkOption.NOFOLLOW_LINKS)) Files.createDirectory(current);
            if (!current.toRealPath(LinkOption.NOFOLLOW_LINKS).startsWith(root))
                throw new SecurityException("FRAMEWORK_ARTIFACT_PARENT_ESCAPE:" + current);
        }
        if (Files.exists(target, LinkOption.NOFOLLOW_LINKS) && Files.isSymbolicLink(target))
            throw new SecurityException("FRAMEWORK_ARTIFACT_SYMLINK:" + target);
        return target;
    }

    private void atomicWrite(Path target, byte[] bytes) throws IOException {
        Path temporary = Files.createTempFile(target.getParent(), target.getFileName().toString(), ".tmp");
        try {
            Files.write(temporary, bytes, StandardOpenOption.TRUNCATE_EXISTING);
            try {
                Files.move(temporary, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException ignored) {
                Files.move(temporary, target, StandardCopyOption.REPLACE_EXISTING);
            }
        } finally {
            Files.deleteIfExists(temporary);
        }
    }
}
