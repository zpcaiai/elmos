package io.elmos.equivalence;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.dataformat.yaml.YAMLFactory;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.github.luben.zstd.ZstdOutputStream;
import io.elmos.equivalence.BehaviorEquivalenceModels.*;

import java.io.BufferedOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.*;
import java.util.*;
import java.util.function.Predicate;

/** Writes the append-only, redacted Batch 9 artifact tree outside both repositories. */
public final class BehaviorEquivalenceArtifactWriter {
    private static final List<String> DIRECTORIES = List.of(
            "equivalence", "environments/source", "environments/target", "environments/shared-recordings",
            "environments/manifests", "corpus/http", "corpus/messages", "corpus/database", "corpus/files",
            "corpus/property", "corpus/metamorphic", "corpus/concurrency", "golden/candidates", "golden/approved",
            "golden/superseded", "golden/invalidated", "observations/source", "observations/target",
            "observations/canonical", "observations/raw", "diffs/http", "diffs/database", "diffs/transactions",
            "diffs/messages", "diffs/files", "diffs/cache", "diffs/errors", "diffs/audit", "diffs/concurrency",
            "external-services/recordings", "external-services/stubs", "external-services/fault-scenarios",
            "external-services/interaction-reports", "data/seeds", "data/anonymized", "data/token-maps",
            "data/retention", "evidence/regression", "evidence/approved-differences", "evidence/unknown",
            "evidence/reproduction-packages", "escalation/source-bug", "escalation/target-regression",
            "escalation/environment", "escalation/collector", "escalation/business-decision", "reports");
    private static final List<String> REPORTS = List.of(
            "behavioral-equivalence-report.json", "public-api-differential-report.json",
            "database-equivalence-report.json", "transaction-atomicity-report.json",
            "message-equivalence-report.json", "file-equivalence-report.json",
            "cache-equivalence-report.json", "exception-equivalence-report.json",
            "audit-equivalence-report.json", "time-randomness-report.json",
            "concurrency-equivalence-report.json", "property-testing-report.json",
            "metamorphic-testing-report.json", "shadow-traffic-report.json",
            "approved-difference-report.json", "unknown-difference-report.json",
            "batch-9-conformance-report.json");
    private final ObjectMapper json;
    private final ObjectMapper yaml;

    public BehaviorEquivalenceArtifactWriter() {
        json = configured(new ObjectMapper());
        yaml = configured(new ObjectMapper(new YAMLFactory()));
    }

    public Map<String,Path> write(Outcome outcome) throws IOException {
        Objects.requireNonNull(outcome, "outcome");
        Path root = outcome.request().artifactWorkspace().toAbsolutePath().normalize();
        rejectRepositoryRoot(root, outcome.request().sourceRepositoryPath(), "source");
        rejectRepositoryRoot(root, outcome.request().targetRepositoryPath(), "target");
        secureDirectories(root);

        Map<String,Path> written = new LinkedHashMap<>();
        written.put("manifest", atomic(root.resolve("equivalence/equivalence-run-manifest.yaml"),
                stream -> yaml.writeValue(stream, outcome.request())));
        written.put("obm-version", atomic(root.resolve("equivalence/obm-version.json"), stream ->
                json.writeValue(stream, Map.of("protocol", "ELMOS-OBM", "version", "1.0", "batch", 9))));
        written.put("observation-points", jsonl(root.resolve("equivalence/observation-points.jsonl.zst"),
                outcome.request().observationPoints()));
        written.put("scenarios", jsonl(root.resolve("equivalence/scenarios.jsonl.zst"), outcome.request().scenarios()));
        written.put("alignments", jsonl(root.resolve("equivalence/alignments.jsonl.zst"),
                outcome.alignment() == null ? List.of() : List.of(outcome.alignment())));
        written.put("comparisons", jsonl(root.resolve("equivalence/comparisons.jsonl.zst"), outcome.comparisons()));
        written.put("difference-clusters", jsonl(root.resolve("equivalence/difference-clusters.jsonl.zst"),
                outcome.repairFeedback()));
        written.put("source-observations", jsonl(root.resolve("observations/source/observations.jsonl.zst"),
                observations(outcome, SystemRole.SOURCE)));
        written.put("target-observations", jsonl(root.resolve("observations/target/observations.jsonl.zst"),
                observations(outcome, SystemRole.TARGET)));
        written.put("gate-results", atomic(root.resolve("equivalence/gate-results.json"),
                stream -> json.writeValue(stream, outcome.report())));
        for (String report : REPORTS) {
            Path path = root.resolve("reports").resolve(report);
            written.put(report, atomic(path, stream -> json.writeValue(stream, reportPayload(report, outcome))));
        }
        return Map.copyOf(written);
    }

    private Object reportPayload(String report, Outcome outcome) {
        Predicate<Comparison> filter = switch (report) {
            case "public-api-differential-report.json" -> value -> value.observationType() == ObservationType.HTTP_RESPONSE;
            case "database-equivalence-report.json" -> value -> value.observationType() == ObservationType.DATABASE_STATE;
            case "transaction-atomicity-report.json" -> value -> value.observationType() == ObservationType.DATABASE_WRITE_TRACE;
            case "message-equivalence-report.json" -> value -> value.observationType() == ObservationType.MESSAGE_EVENT;
            case "file-equivalence-report.json" -> value -> Set.of(ObservationType.FILE_OUTPUT, ObservationType.OBJECT_STORAGE_OUTPUT).contains(value.observationType());
            case "cache-equivalence-report.json" -> value -> value.observationType() == ObservationType.CACHE_STATE;
            case "exception-equivalence-report.json" -> value -> value.observationType() == ObservationType.EXCEPTION;
            case "audit-equivalence-report.json" -> value -> value.observationType() == ObservationType.AUDIT;
            case "concurrency-equivalence-report.json" -> value -> value.observationType() == ObservationType.CONCURRENCY;
            case "approved-difference-report.json" -> value -> value.status() == ComparisonStatus.APPROVED_CHANGE;
            case "unknown-difference-report.json" -> value -> Set.of(ComparisonStatus.UNKNOWN, ComparisonStatus.NOT_COMPARABLE).contains(value.status());
            default -> value -> true;
        };
        List<Comparison> selected = outcome.comparisons().stream().filter(filter).toList();
        return Map.of("report", report, "equivalenceRunId", outcome.request().equivalenceRunId(),
                "conformance", outcome.report(), "comparisonCount", selected.size(), "comparisons", selected);
    }

    private static List<Observation> observations(Outcome outcome, SystemRole role) {
        return outcome.cleanRuns().stream().flatMap(run -> run.scenarios().stream())
                .flatMap(execution -> (role == SystemRole.SOURCE
                        ? execution.sourceObservations() : execution.targetObservations()).stream()).toList();
    }

    private Path jsonl(Path target, Collection<?> values) throws IOException {
        return atomic(target, raw -> {
            try (ZstdOutputStream zstd = new ZstdOutputStream(new BufferedOutputStream(raw))) {
                for (Object value : values) {
                    zstd.write(json.writeValueAsBytes(value));
                    zstd.write('\n');
                }
            }
        });
    }

    private Path atomic(Path target, IoWriter writer) throws IOException {
        assertSafeTarget(target);
        if (Files.exists(target, LinkOption.NOFOLLOW_LINKS))
            throw new FileAlreadyExistsException("Batch 9 evidence is append-only: " + target);
        Path temporary = Files.createTempFile(target.getParent(), ".batch9-", ".tmp");
        try {
            try (OutputStream output = Files.newOutputStream(temporary, StandardOpenOption.WRITE)) { writer.write(output); }
            try { Files.move(temporary, target, StandardCopyOption.ATOMIC_MOVE); }
            catch (AtomicMoveNotSupportedException ignored) { Files.move(temporary, target); }
            return target;
        } finally { Files.deleteIfExists(temporary); }
    }

    private static void secureDirectories(Path root) throws IOException {
        if (Files.exists(root, LinkOption.NOFOLLOW_LINKS) && Files.isSymbolicLink(root))
            throw new IOException("artifact workspace cannot be a symbolic link");
        if (!Files.exists(root, LinkOption.NOFOLLOW_LINKS)) Files.createDirectories(root);
        for (String directory : DIRECTORIES) {
            Path current = root;
            for (Path part : Path.of(directory)) {
                current = current.resolve(part);
                if (Files.exists(current, LinkOption.NOFOLLOW_LINKS)) {
                    if (Files.isSymbolicLink(current) || !Files.isDirectory(current, LinkOption.NOFOLLOW_LINKS))
                        throw new IOException("unsafe artifact directory: " + current);
                } else Files.createDirectory(current);
            }
        }
    }

    private static void assertSafeTarget(Path target) throws IOException {
        Path parent = target.getParent();
        if (Files.isSymbolicLink(parent)) throw new IOException("symbolic-link parent rejected: " + parent);
    }

    private static void rejectRepositoryRoot(Path root, Path repository, String role) {
        Path normalized = repository.toAbsolutePath().normalize();
        if (root.equals(normalized) || root.startsWith(normalized))
            throw new IllegalArgumentException("artifact workspace cannot be inside the " + role + " repository");
    }

    private static ObjectMapper configured(ObjectMapper mapper) {
        mapper.registerModule(new JavaTimeModule());
        mapper.setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
        mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
        return mapper;
    }

    @FunctionalInterface private interface IoWriter { void write(OutputStream output) throws IOException; }
}
