package io.elmos.companyseries;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

import java.io.IOException;
import java.nio.file.*;
import java.util.LinkedHashMap;
import java.util.Map;

import static io.elmos.companyseries.CompanySeriesModels.*;

/** Writes immutable-shape company-series projections without performing external business actions. */
public final class CompanySeriesArtifactWriter {
    private final ObjectMapper json = new ObjectMapper().registerModule(new JavaTimeModule())
            .setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);

    public Map<String, Path> write(Outcome outcome) throws IOException {
        ProgramDefinition definition = outcome.definition();
        Request request = outcome.request();
        Path workspace = request.artifactWorkspace().toAbsolutePath().normalize();
        Path repository = request.repositoryPath().toAbsolutePath().normalize();
        if (workspace.startsWith(repository))
            throw new IllegalArgumentException("artifact workspace must remain outside the repository");
        Path root = workspace.resolve(definition.artifactRoot()).normalize();
        if (!root.startsWith(workspace)) throw new IllegalArgumentException("artifact path escaped workspace");
        Files.createDirectories(root);
        for (String directory : definition.artifactDirectories())
            Files.createDirectories(root.resolve(directory));

        Map<String, Path> written = new LinkedHashMap<>();
        written.put("program.json", atomic(root.resolve("program.json"), Map.ofEntries(
                Map.entry("batch", definition.batch()), Map.entry("model", definition.model()),
                Map.entry("program_id", request.programId()), Map.entry("source_version", request.sourceVersion()),
                Map.entry("organization_id", request.organizationId()), Map.entry("owner_id", request.humanOwnerId()),
                Map.entry("dimensions", definition.dimensions()), Map.entry("observed_at", request.observedAt()),
                Map.entry("evidence_refs", request.admissionEvidenceRefs()),
                Map.entry("external_operation_executed", false))));
        written.put("evidence-pack.json", atomic(root.resolve("evidence-pack.json"), Map.of(
                "batch", definition.batch(), "program_id", request.programId(),
                "source_version", request.sourceVersion(), "organization_id", request.organizationId(),
                "gate_evidence", outcome.gateEvidence().values(),
                "complete", outcome.report().evidenceComplete(), "external_operation_executed", false)));
        for (String report : definition.reports()) {
            Path file = root.resolve("reports").resolve(report);
            written.put(report, atomic(file, Map.of(
                    "report", report, "batch", definition.batch(), "model", definition.model(),
                    "conformance", outcome.report(), "external_operation_executed", false)));
        }
        return Map.copyOf(written);
    }

    private Path atomic(Path target, Object value) throws IOException {
        Files.createDirectories(target.getParent());
        Path temporary = Files.createTempFile(target.getParent(), ".company-series-", ".tmp");
        try {
            json.writerWithDefaultPrettyPrinter().writeValue(temporary.toFile(), value);
            try {
                Files.move(temporary, target, StandardCopyOption.ATOMIC_MOVE,
                        StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException ignored) {
                Files.move(temporary, target, StandardCopyOption.REPLACE_EXISTING);
            }
            return target;
        } finally {
            Files.deleteIfExists(temporary);
        }
    }
}
