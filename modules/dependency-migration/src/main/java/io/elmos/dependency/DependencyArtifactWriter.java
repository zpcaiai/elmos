package io.elmos.dependency;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.LinkedHashMap;
import java.util.Map;

import static io.elmos.dependency.DependencyMigrationModels.RunResult;

/** Writes the governed Batch 6 workspace; it never edits the target repository or lockfiles. */
public final class DependencyArtifactWriter {
    private final ObjectMapper mapper = new ObjectMapper().registerModule(new JavaTimeModule()).enable(SerializationFeature.INDENT_OUTPUT);

    public Map<String,Path> write(Path migrationWorkspace, RunResult result) throws IOException {
        Map<String,Object> artifacts = new LinkedHashMap<>();
        artifacts.put("dependencies/dependency-manifest.json", result.manifest());
        artifacts.put("dependencies/resolved-graphs.json", result.graphs());
        artifacts.put("dependencies/used-api-surface.json", result.usages());
        artifacts.put("dependencies/api-semantic-profiles.json", result.profiles());
        artifacts.put("mappings/dependency-decisions.json", result.decisions());
        artifacts.put("patches/build-patches.json", result.patches());
        artifacts.put("reports/build-validation.json", result.buildValidations());
        artifacts.put("reports/api-contract-validation.json", result.contractValidations());
        artifacts.put("reports/batch-6-conformance.json", result.conformance());
        Map<String,Path> written = new LinkedHashMap<>();
        for (Map.Entry<String,Object> entry : artifacts.entrySet()) {
            Path target = migrationWorkspace.resolve(entry.getKey()).normalize();
            if (!target.startsWith(migrationWorkspace.normalize())) throw new IOException("artifact escaped migration workspace");
            Files.createDirectories(target.getParent());
            byte[] bytes = mapper.writeValueAsBytes(entry.getValue());
            Files.write(target, bytes, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING, StandardOpenOption.WRITE);
            written.put(entry.getKey(), target);
        }
        return Map.copyOf(written);
    }
}
