package io.elmos.intake;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.dataformat.yaml.YAMLFactory;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Objects;

import static io.elmos.intake.IntakeModels.*;

/** Writes deterministic machine-readable Batch 1 control artifacts; source bytes remain in the snapshot store. */
public final class MigrationWorkspaceWriter {
    private final ObjectMapper json = new ObjectMapper().findAndRegisterModules().enable(SerializationFeature.INDENT_OUTPUT)
            .enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);
    private final ObjectMapper yaml = new ObjectMapper(new YAMLFactory()).findAndRegisterModules()
            .enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);

    public void write(Path requestedWorkspace, IntakeBundle bundle) {
        Objects.requireNonNull(bundle, "bundle"); Path workspace = secureWorkspace(requestedWorkspace);
        Path manifests = workspace.resolve("manifests"); String digest = bundle.snapshot().snapshotId().substring("sha256:".length());
        try {
            Files.createDirectories(manifests); Files.createDirectories(workspace.resolve("snapshots").resolve(digest));
            Files.createDirectories(workspace.resolve("logs/build")); Files.createDirectories(workspace.resolve("logs/test"));
            Files.createDirectories(workspace.resolve("evidence/dependency")); Files.createDirectories(workspace.resolve("evidence/framework")); Files.createDirectories(workspace.resolve("evidence/module"));
            writeJson(manifests.resolve("repository-snapshot.json"), bundle.snapshot());
            writeJson(manifests.resolve("project-fingerprint.json"), bundle.fingerprint());
            writeJson(manifests.resolve("build-model.json"), bundle.buildModel());
            writeJson(manifests.resolve("source-inventory.json"), bundle.inventory());
            writeJson(manifests.resolve("dependency-graph.json"), bundle.dependencyGraph());
            writeJson(manifests.resolve("baseline-report.json"), bundle.baseline());
            writeYaml(manifests.resolve("sandbox-policy.yaml"), bundle.sandboxPolicy());
            writeYaml(manifests.resolve("migration-manifest.yaml"), bundle.migrationManifest());
            writeJson(workspace.resolve("snapshots").resolve(digest).resolve("snapshot-ref.json"), bundle.snapshot());
        } catch (IOException error) { throw new IllegalStateException("MIGRATION_WORKSPACE_WRITE_FAILED", error); }
    }

    private void writeJson(Path target, Object value) throws IOException { atomic(target, json.writeValueAsBytes(value)); }
    private void writeYaml(Path target, Object value) throws IOException { atomic(target, yaml.writeValueAsBytes(value)); }
    private static void atomic(Path target, byte[] bytes) throws IOException {
        Path temporary = Files.createTempFile(target.getParent(), target.getFileName().toString(), ".tmp");
        try { Files.write(temporary, bytes); Files.move(temporary, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING); }
        finally { Files.deleteIfExists(temporary); }
    }
    private static Path secureWorkspace(Path requested) {
        Objects.requireNonNull(requested, "workspace"); Path absolute = requested.toAbsolutePath().normalize();
        try {
            if (Files.exists(absolute, LinkOption.NOFOLLOW_LINKS) && (Files.isSymbolicLink(absolute) || !Files.isDirectory(absolute, LinkOption.NOFOLLOW_LINKS)))
                throw new SecurityException("workspace must be a real directory");
            Files.createDirectories(absolute); return absolute.toRealPath(LinkOption.NOFOLLOW_LINKS);
        } catch (IOException error) { throw new IllegalArgumentException("WORKSPACE_UNAVAILABLE", error); }
    }
}
