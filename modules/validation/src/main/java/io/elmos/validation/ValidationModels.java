package io.elmos.validation;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class ValidationModels {
    private ValidationModels() {}

    public enum Status { PASS, PASS_WITH_WARNINGS, FAIL, MISSING, INCONCLUSIVE }
    public enum Severity { INFO, WARNING, ERROR, CRITICAL }
    public enum TestStatus { PASSED, FAILED, SKIPPED, ABORTED, NOT_RUN }
    public enum Domain { ENVIRONMENT, BUILD, TEST, SERVICE, HTTP_API, JAVA_API, SERIALIZATION,
        MESSAGE, DATABASE, TRANSACTION, PERFORMANCE, SECURITY }

    public record Environment(String environmentId, String workspaceId, String sourceSnapshotId,
                              String commitSha, String jdkDigest, String buildToolVersion,
                              Map<String,String> containerImageDigests, boolean reusableContainers,
                              String networkPolicyId, String fixtureHash) {
        public Environment {
            require(environmentId, "environmentId"); require(workspaceId, "workspaceId"); require(sourceSnapshotId, "sourceSnapshotId");
            require(commitSha, "commitSha"); digest(jdkDigest, "jdkDigest"); require(buildToolVersion, "buildToolVersion");
            containerImageDigests = Map.copyOf(containerImageDigests); require(networkPolicyId, "networkPolicyId");
            digest(fixtureHash, "fixtureHash");
        }
    }

    public record BuildSnapshot(String environmentId, Map<String,Status> stages, Set<String> artifactHashes,
                                Set<String> warnings, String commandHash, boolean cleanBuild,
                                List<String> evidenceRefs) {
        public BuildSnapshot {
            stages = Map.copyOf(stages); artifactHashes = Set.copyOf(artifactHashes); warnings = Set.copyOf(warnings);
            digest(commandHash, "commandHash"); evidenceRefs = List.copyOf(evidenceRefs);
        }
    }

    public record TestCase(String engine, String className, String methodName, String parameterIdentity,
                           TestStatus status, String failureFingerprint, long durationMillis,
                           boolean testManagedTransaction) {
        public TestCase {
            require(engine, "engine"); require(className, "className"); require(methodName, "methodName");
            parameterIdentity = parameterIdentity == null ? "" : parameterIdentity;
            if (durationMillis < 0) throw new IllegalArgumentException("test duration is invalid");
        }
        public String identity() { return engine + ":" + className + "#" + methodName + "[" + parameterIdentity + "]"; }
    }

    public record HttpContract(Map<String,HttpOperation> operations) {
        public HttpContract { operations = Map.copyOf(operations); }
    }
    public record HttpOperation(Set<String> requiredRequestFields, Set<String> responseFields,
                                Set<String> securitySchemes) {
        public HttpOperation {
            requiredRequestFields = Set.copyOf(requiredRequestFields); responseFields = Set.copyOf(responseFields);
            securitySchemes = Set.copyOf(securitySchemes);
        }
    }
    public record JavaApi(Set<String> binarySignatures, Set<String> sourceSignatures) {
        public JavaApi { binarySignatures = Set.copyOf(binarySignatures); sourceSignatures = Set.copyOf(sourceSignatures); }
    }
    public record SerializationContract(Set<String> requiredFields, Map<String,String> fieldFormats,
                                        Set<String> enumValues, Map<String,String> discriminatorMappings) {
        public SerializationContract {
            requiredFields = Set.copyOf(requiredFields); fieldFormats = Map.copyOf(fieldFormats);
            enumValues = Set.copyOf(enumValues); discriminatorMappings = Map.copyOf(discriminatorMappings);
        }
    }
    public record DatabaseSchema(Map<String,Column> columns, Set<String> constraints, Set<String> indexes) {
        public DatabaseSchema { columns = Map.copyOf(columns); constraints = Set.copyOf(constraints); indexes = Set.copyOf(indexes); }
    }
    public record Column(String type, boolean nullable, String defaultValue) { public Column { require(type, "column.type"); } }

    public record TransactionObservation(String scenarioId, boolean committed, boolean rolledBack,
                                         String propagation, String isolation, int writes,
                                         boolean asyncBoundary, boolean testManagedTransaction,
                                         String traceHash) {
        public TransactionObservation { require(scenarioId, "scenarioId"); digest(traceHash, "traceHash"); }
    }

    public record PerformanceSample(String scenarioId, List<Double> latencyMillis, double throughput,
                                    double cpuSeconds, long peakMemoryBytes, String environmentId) {
        public PerformanceSample {
            require(scenarioId, "scenarioId"); latencyMillis = List.copyOf(latencyMillis); require(environmentId, "environmentId");
            if (latencyMillis.isEmpty() || latencyMillis.stream().anyMatch(value -> value < 0) || throughput < 0 || cpuSeconds < 0 || peakMemoryBytes < 0)
                throw new IllegalArgumentException("performance sample is invalid");
        }
    }

    public record Finding(String code, Domain domain, Severity severity, String message,
                          List<String> evidenceRefs) {
        public Finding { require(code, "finding.code"); require(message, "finding.message"); evidenceRefs = List.copyOf(evidenceRefs); }
    }
    public record DomainResult(Domain domain, Status status, List<Finding> findings,
                               List<String> evidenceRefs, double confidence) {
        public DomainResult {
            findings = List.copyOf(findings); evidenceRefs = List.copyOf(evidenceRefs);
            if (confidence < 0 || confidence > 1) throw new IllegalArgumentException("confidence is outside range");
        }
    }
    public record ValidationPolicy(String version, Set<Domain> requiredDomains,
                                   Set<String> warningCodes, Set<String> hardFailCodes,
                                   double minimumConfidence) {
        public ValidationPolicy {
            require(version, "policy.version"); requiredDomains = Set.copyOf(requiredDomains);
            warningCodes = Set.copyOf(warningCodes); hardFailCodes = Set.copyOf(hardFailCodes);
            if (minimumConfidence < 0 || minimumConfidence > 1) throw new IllegalArgumentException("minimum confidence is invalid");
        }
    }
    public record ValidationDecision(String schemaVersion, String decisionId, String policyVersion,
                                     String baselineEnvironmentId, String migratedEnvironmentId,
                                     Status status, List<DomainResult> domainResults,
                                     List<String> blockingReasons, double confidence,
                                     Instant decidedAt, List<String> evidenceRefs) {
        public ValidationDecision {
            if (!"1.0".equals(schemaVersion)) throw new IllegalArgumentException("unsupported schema version");
            domainResults = List.copyOf(domainResults); blockingReasons = List.copyOf(blockingReasons); evidenceRefs = List.copyOf(evidenceRefs);
        }
    }

    static void require(String value, String field) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(field + " is required");
    }
    static void digest(String value, String field) {
        if (value == null || !value.matches("(?:sha256:)?[0-9a-f]{64}")) throw new IllegalArgumentException(field + " must be a sha256 digest");
    }
}
