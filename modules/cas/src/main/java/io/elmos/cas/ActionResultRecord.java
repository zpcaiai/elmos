package io.elmos.cas;

import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.TreeMap;

/**
 * ELMOS-CAS-023. The cached statement of what an action produced, shaped to
 * {@code schemas/action-result.schema.json}.
 *
 * <p>Logs are referenced by digest, never inlined. Two reasons, both practical: a build log is
 * routinely larger than every artifact it describes, and a log is the single most common place
 * for a secret to end up. Storing it as content means it is redacted once, at the boundary, and
 * the cache entry stays small enough to be read on every lookup.
 */
public record ActionResultRecord(String schemaVersion,
                                 String actionId,
                                 int attempt,
                                 int leaseGeneration,
                                 String receiptId,
                                 Status status,
                                 String startedAt,
                                 String finishedAt,
                                 int exitCode,
                                 CasDigest outputManifestDigest,
                                 Optional<CasDigest> stdoutDigest,
                                 Optional<CasDigest> stderrDigest,
                                 ResourceUsage resourceUsage,
                                 Map<String, Double> cost,
                                 Optional<FailureClass> failureClass,
                                 Optional<String> failureMessage,
                                 ValidationStatus validationStatus,
                                 CasDigest provenanceDigest) {

    public static final String SCHEMA_VERSION = "1.0";

    public enum Status {
        SUCCEEDED,
        FAILED,
        CANCELLED,
        UNKNOWN_RESULT
    }

    public enum ValidationStatus {
        NOT_RUN,
        PASS,
        FAIL,
        PARTIAL
    }

    /**
     * The skill's failure taxonomy. {@link ActionCache} keys its caching decision off this: a
     * CODE failure is a property of the inputs and reproduces, an ENVIRONMENT or CAPACITY failure
     * is a property of the moment and must never be remembered as a result.
     */
    public enum FailureClass {
        ENVIRONMENT(false),
        DEPENDENCY(false),
        CODE(true),
        POLICY(true),
        SECURITY(true),
        DATA(false),
        CAPACITY(false),
        PROVIDER(false),
        UNKNOWN(false);

        private final boolean deterministicGivenInputs;

        FailureClass(boolean deterministicGivenInputs) {
            this.deterministicGivenInputs = deterministicGivenInputs;
        }

        public boolean deterministicGivenInputs() {
            return deterministicGivenInputs;
        }
    }

    public record ResourceUsage(double cpuSeconds, double maxMemoryMb, long readBytes, long writtenBytes,
                                double gpuSeconds, double wallSeconds) {
        public ResourceUsage {
            if (!Double.isFinite(cpuSeconds) || !Double.isFinite(maxMemoryMb)
                    || !Double.isFinite(gpuSeconds) || !Double.isFinite(wallSeconds)
                    || cpuSeconds < 0 || maxMemoryMb < 0 || readBytes < 0 || writtenBytes < 0
                    || gpuSeconds < 0 || wallSeconds < 0) {
                throw new IllegalArgumentException(
                        "resource usage must be finite and must not be negative");
            }
        }
    }

    public ActionResultRecord {
        schemaVersion = CasText.required(schemaVersion, "schemaVersion");
        actionId = CasText.required(actionId, "actionId");
        if (attempt < 1) {
            throw new IllegalArgumentException("attempt starts at 1");
        }
        if (leaseGeneration < 1) {
            throw new IllegalArgumentException("leaseGeneration starts at 1");
        }
        receiptId = CasText.required(receiptId, "receiptId");
        Objects.requireNonNull(status, "status");
        startedAt = CasText.required(startedAt, "startedAt");
        finishedAt = CasText.required(finishedAt, "finishedAt");
        Objects.requireNonNull(outputManifestDigest, "outputManifestDigest");
        Objects.requireNonNull(stdoutDigest, "stdoutDigest");
        Objects.requireNonNull(stderrDigest, "stderrDigest");
        Objects.requireNonNull(resourceUsage, "resourceUsage");
        TreeMap<String, Double> canonicalCost = new TreeMap<>();
        Objects.requireNonNull(cost, "cost").forEach((name, value) -> {
            String key = CasText.required(name, "cost name");
            if (value == null || !Double.isFinite(value)) {
                throw new IllegalArgumentException("cost values must be finite");
            }
            canonicalCost.put(key, value);
        });
        cost = Map.copyOf(canonicalCost);
        Objects.requireNonNull(failureClass, "failureClass");
        Objects.requireNonNull(failureMessage, "failureMessage");
        Objects.requireNonNull(validationStatus, "validationStatus");
        Objects.requireNonNull(provenanceDigest, "provenanceDigest");
        if (status == Status.SUCCEEDED && exitCode != 0) {
            throw new IllegalArgumentException("SUCCEEDED result cannot carry exit code " + exitCode);
        }
        if (status == Status.FAILED && failureClass.isEmpty()) {
            throw new IllegalArgumentException("FAILED result must carry a failure class");
        }
    }

    public static ActionResultRecord succeeded(String actionId, String receiptId, CasDigest outputManifest,
                                               CasDigest provenance, ResourceUsage usage,
                                               String startedAt, String finishedAt) {
        return new ActionResultRecord(SCHEMA_VERSION, actionId, 1, 1, receiptId, Status.SUCCEEDED,
                startedAt, finishedAt, 0, outputManifest, Optional.empty(), Optional.empty(), usage,
                Map.of(), Optional.empty(), Optional.empty(), ValidationStatus.PASS, provenance);
    }

    public static ActionResultRecord failed(String actionId, String receiptId, int exitCode,
                                            FailureClass failureClass, String message,
                                            CasDigest outputManifest, CasDigest provenance,
                                            ResourceUsage usage, String startedAt, String finishedAt) {
        return new ActionResultRecord(SCHEMA_VERSION, actionId, 1, 1, receiptId, Status.FAILED,
                startedAt, finishedAt, exitCode, outputManifest, Optional.empty(), Optional.empty(), usage,
                Map.of(), Optional.of(failureClass), Optional.of(message), ValidationStatus.FAIL, provenance);
    }

    public ActionResultRecord withLogs(CasDigest stdout, CasDigest stderr) {
        return new ActionResultRecord(schemaVersion, actionId, attempt, leaseGeneration, receiptId, status,
                startedAt, finishedAt, exitCode, outputManifestDigest, Optional.of(stdout), Optional.of(stderr),
                resourceUsage, cost, failureClass, failureMessage, validationStatus, provenanceDigest);
    }

    public boolean reusable() {
        return status == Status.SUCCEEDED
                || (status == Status.FAILED && failureClass.map(FailureClass::deterministicGivenInputs).orElse(false));
    }
}
