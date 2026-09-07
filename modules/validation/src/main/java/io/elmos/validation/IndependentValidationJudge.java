package io.elmos.validation;

import io.elmos.validation.ValidationModels.*;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;

public final class IndependentValidationJudge {
    public DomainResult compareEnvironments(Environment baseline, Environment migrated) {
        List<Finding> findings = new ArrayList<>();
        if (baseline.workspaceId().equals(migrated.workspaceId())) findings.add(finding("VALIDATION_WORKSPACE_NOT_ISOLATED", Domain.ENVIRONMENT, Severity.CRITICAL));
        if (baseline.environmentId().equals(migrated.environmentId())) findings.add(finding("VALIDATION_ENVIRONMENT_ID_REUSED", Domain.ENVIRONMENT, Severity.ERROR));
        if (!baseline.jdkDigest().equals(migrated.jdkDigest()) || !baseline.buildToolVersion().equals(migrated.buildToolVersion())
                || !baseline.containerImageDigests().equals(migrated.containerImageDigests())
                || !baseline.fixtureHash().equals(migrated.fixtureHash()))
            findings.add(finding("VALIDATION_ENVIRONMENT_NOT_COMPARABLE", Domain.ENVIRONMENT, Severity.ERROR));
        if (baseline.reusableContainers() || migrated.reusableContainers()) findings.add(finding("TESTCONTAINERS_REUSE_FORBIDDEN", Domain.ENVIRONMENT, Severity.CRITICAL));
        if (baseline.containerImageDigests().values().stream().anyMatch(value -> !value.matches("sha256:[0-9a-f]{64}"))
                || migrated.containerImageDigests().values().stream().anyMatch(value -> !value.matches("sha256:[0-9a-f]{64}")))
            findings.add(finding("TESTCONTAINERS_IMAGE_NOT_PINNED", Domain.ENVIRONMENT, Severity.CRITICAL));
        return result(Domain.ENVIRONMENT, findings, evidence(baseline.environmentId(), migrated.environmentId()));
    }

    public DomainResult compareBuild(BuildSnapshot baseline, BuildSnapshot migrated) {
        List<Finding> findings = new ArrayList<>();
        if (!baseline.cleanBuild() || !migrated.cleanBuild()) findings.add(finding("BUILD_NOT_CLEAN", Domain.BUILD, Severity.ERROR));
        Set<String> stages = new TreeSet<>(baseline.stages().keySet()); stages.addAll(migrated.stages().keySet());
        for (String stage : stages) {
            Status before = baseline.stages().get(stage), after = migrated.stages().get(stage);
            if (before == null || after == null || after == Status.MISSING) findings.add(finding("BUILD_STAGE_NOT_RUN:" + stage, Domain.BUILD, Severity.CRITICAL));
            else if ((before == Status.PASS || before == Status.PASS_WITH_WARNINGS) && after == Status.FAIL)
                findings.add(finding("BUILD_REGRESSION:" + stage, Domain.BUILD, Severity.CRITICAL));
            else if (before == Status.FAIL && after == Status.FAIL)
                findings.add(new Finding("BASELINE_FAILURE_PRESERVED:" + stage, Domain.BUILD, Severity.INFO,
                        "Baseline failure remains and is not attributed to migration", List.of()));
        }
        Set<String> newWarnings = new TreeSet<>(migrated.warnings()); newWarnings.removeAll(baseline.warnings());
        if (!newWarnings.isEmpty()) findings.add(new Finding("BUILD_NEW_WARNINGS", Domain.BUILD, Severity.WARNING,
                "Migrated build introduced warnings: " + newWarnings, List.of()));
        return result(Domain.BUILD, findings, concat(baseline.evidenceRefs(), migrated.evidenceRefs()));
    }

    public DomainResult compareTests(List<TestCase> baseline, List<TestCase> migrated) {
        return compareTests(baseline, migrated, List.of());
    }

    public DomainResult compareTests(List<TestCase> baseline, List<TestCase> migrated, List<String> evidenceRefs) {
        List<Finding> findings = new ArrayList<>();
        Map<String,TestCase> before = indexTests(baseline), after = indexTests(migrated);
        for (Map.Entry<String,TestCase> entry : before.entrySet()) {
            TestCase original = entry.getValue(), current = after.get(entry.getKey());
            if (current == null || current.status() == TestStatus.NOT_RUN) findings.add(finding("TEST_MISSING:" + entry.getKey(), Domain.TEST, Severity.CRITICAL));
            else if (current.status() == TestStatus.SKIPPED && original.status() != TestStatus.SKIPPED)
                findings.add(finding("TEST_SILENTLY_SKIPPED:" + entry.getKey(), Domain.TEST, Severity.CRITICAL));
            else if (original.status() == TestStatus.PASSED && current.status() == TestStatus.FAILED)
                findings.add(finding("TEST_NEW_FAILURE:" + entry.getKey(), Domain.TEST, Severity.CRITICAL));
            else if (original.status() == TestStatus.FAILED && current.status() == TestStatus.FAILED
                    && !Objects.equals(original.failureFingerprint(), current.failureFingerprint()))
                findings.add(finding("TEST_FAILURE_CHANGED:" + entry.getKey(), Domain.TEST, Severity.ERROR));
            else if (original.status() == TestStatus.FAILED && current.status() == TestStatus.FAILED)
                findings.add(new Finding("BASELINE_TEST_FAILURE_PRESERVED:" + entry.getKey(), Domain.TEST, Severity.INFO,
                        "Pre-existing failure fingerprint is unchanged", List.of()));
        }
        return result(Domain.TEST, findings, evidenceRefs);
    }

    public DomainResult compareHttp(HttpContract baseline, HttpContract migrated) {
        return compareHttp(baseline, migrated, List.of());
    }

    public DomainResult compareHttp(HttpContract baseline, HttpContract migrated, List<String> evidenceRefs) {
        List<Finding> findings = new ArrayList<>();
        for (Map.Entry<String,HttpOperation> entry : baseline.operations().entrySet()) {
            HttpOperation after = migrated.operations().get(entry.getKey());
            if (after == null) { findings.add(finding("HTTP_OPERATION_REMOVED:" + entry.getKey(), Domain.HTTP_API, Severity.CRITICAL)); continue; }
            Set<String> addedRequired = difference(after.requiredRequestFields(), entry.getValue().requiredRequestFields());
            if (!addedRequired.isEmpty()) findings.add(finding("HTTP_REQUEST_REQUIRED_FIELD_ADDED:" + entry.getKey(), Domain.HTTP_API, Severity.CRITICAL));
            if (!after.responseFields().containsAll(entry.getValue().responseFields())) findings.add(finding("HTTP_RESPONSE_FIELD_REMOVED:" + entry.getKey(), Domain.HTTP_API, Severity.CRITICAL));
            if (!after.securitySchemes().equals(entry.getValue().securitySchemes())) findings.add(finding("HTTP_SECURITY_CONTRACT_CHANGED:" + entry.getKey(), Domain.HTTP_API, Severity.CRITICAL));
        }
        return result(Domain.HTTP_API, findings, evidenceRefs);
    }

    public DomainResult compareJava(JavaApi baseline, JavaApi migrated) {
        return compareJava(baseline, migrated, List.of());
    }

    public DomainResult compareJava(JavaApi baseline, JavaApi migrated, List<String> evidenceRefs) {
        List<Finding> findings = new ArrayList<>();
        Set<String> binaryRemoved = difference(baseline.binarySignatures(), migrated.binarySignatures());
        Set<String> sourceRemoved = difference(baseline.sourceSignatures(), migrated.sourceSignatures());
        if (!binaryRemoved.isEmpty()) findings.add(finding("JAVA_BINARY_API_REMOVED:" + binaryRemoved, Domain.JAVA_API, Severity.CRITICAL));
        if (!sourceRemoved.isEmpty()) findings.add(finding("JAVA_SOURCE_API_REMOVED:" + sourceRemoved, Domain.JAVA_API, Severity.ERROR));
        return result(Domain.JAVA_API, findings, evidenceRefs);
    }

    public DomainResult compareSerialization(SerializationContract baseline, SerializationContract migrated, Domain domain) {
        return compareSerialization(baseline, migrated, domain, List.of());
    }

    public DomainResult compareSerialization(SerializationContract baseline, SerializationContract migrated,
                                             Domain domain, List<String> evidenceRefs) {
        if (domain != Domain.SERIALIZATION && domain != Domain.MESSAGE) throw new IllegalArgumentException("serialization comparator domain is invalid");
        List<Finding> findings = new ArrayList<>();
        Set<String> newlyRequired = difference(migrated.requiredFields(), baseline.requiredFields());
        if (!newlyRequired.isEmpty()) findings.add(finding("SERIALIZATION_REQUIRED_FIELD_ADDED:" + newlyRequired, domain, Severity.CRITICAL));
        for (Map.Entry<String,String> format : baseline.fieldFormats().entrySet())
            if (!Objects.equals(format.getValue(), migrated.fieldFormats().get(format.getKey())))
                findings.add(finding("SERIALIZATION_FORMAT_CHANGED:" + format.getKey(), domain, Severity.CRITICAL));
        if (!migrated.enumValues().containsAll(baseline.enumValues())) findings.add(finding("SERIALIZATION_ENUM_VALUE_REMOVED", domain, Severity.CRITICAL));
        if (!migrated.discriminatorMappings().equals(baseline.discriminatorMappings())) findings.add(finding("SERIALIZATION_DISCRIMINATOR_CHANGED", domain, Severity.CRITICAL));
        return result(domain, findings, evidenceRefs);
    }

    public DomainResult compareDatabase(DatabaseSchema baseline, DatabaseSchema migrated) {
        return compareDatabase(baseline, migrated, List.of());
    }

    public DomainResult compareDatabase(DatabaseSchema baseline, DatabaseSchema migrated, List<String> evidenceRefs) {
        List<Finding> findings = new ArrayList<>();
        Set<String> removed = difference(baseline.columns().keySet(), migrated.columns().keySet());
        Set<String> added = difference(migrated.columns().keySet(), baseline.columns().keySet());
        if (!removed.isEmpty() && !added.isEmpty()) findings.add(finding("DATABASE_RENAME_REQUIRES_CONFIRMATION", Domain.DATABASE, Severity.ERROR));
        for (Map.Entry<String,Column> entry : baseline.columns().entrySet()) {
            Column after = migrated.columns().get(entry.getKey());
            if (after == null) { findings.add(finding("DATABASE_COLUMN_REMOVED:" + entry.getKey(), Domain.DATABASE, Severity.CRITICAL)); continue; }
            if (!entry.getValue().type().equals(after.type())) findings.add(finding("DATABASE_COLUMN_TYPE_CHANGED:" + entry.getKey(), Domain.DATABASE, Severity.CRITICAL));
            if (entry.getValue().nullable() && !after.nullable()) findings.add(finding("DATABASE_NULLABLE_TIGHTENED:" + entry.getKey(), Domain.DATABASE, Severity.CRITICAL));
        }
        return result(Domain.DATABASE, findings, evidenceRefs);
    }

    public DomainResult compareTransactions(List<TransactionObservation> baseline, List<TransactionObservation> migrated) {
        return compareTransactions(baseline, migrated, List.of());
    }

    public DomainResult compareTransactions(List<TransactionObservation> baseline, List<TransactionObservation> migrated,
                                            List<String> evidenceRefs) {
        List<Finding> findings = new ArrayList<>();
        Map<String,TransactionObservation> after = new TreeMap<>(); migrated.forEach(value -> after.put(value.scenarioId(), value));
        for (TransactionObservation before : baseline) {
            TransactionObservation current = after.get(before.scenarioId());
            if (current == null) { findings.add(finding("TRANSACTION_SCENARIO_MISSING:" + before.scenarioId(), Domain.TRANSACTION, Severity.CRITICAL)); continue; }
            if (before.rolledBack() && current.committed()) findings.add(finding("TRANSACTION_ROLLBACK_CHANGED_TO_COMMIT:" + before.scenarioId(), Domain.TRANSACTION, Severity.CRITICAL));
            if (!Objects.equals(before.propagation(), current.propagation()) || !Objects.equals(before.isolation(), current.isolation()))
                findings.add(finding("TRANSACTION_BOUNDARY_CHANGED:" + before.scenarioId(), Domain.TRANSACTION, Severity.CRITICAL));
            if (before.testManagedTransaction() || current.testManagedTransaction())
                findings.add(finding("TRANSACTION_TEST_MANAGED_EVIDENCE_INSUFFICIENT:" + before.scenarioId(), Domain.TRANSACTION, Severity.ERROR));
        }
        return result(Domain.TRANSACTION, findings, evidenceRefs);
    }

    public DomainResult comparePerformance(PerformanceSample baseline, PerformanceSample migrated,
                                           double warningThreshold, double failThreshold, double maximumNoise) {
        return comparePerformance(baseline, migrated, warningThreshold, failThreshold, maximumNoise, List.of());
    }

    public DomainResult comparePerformance(PerformanceSample baseline, PerformanceSample migrated,
                                           double warningThreshold, double failThreshold, double maximumNoise,
                                           List<String> evidenceRefs) {
        List<Finding> findings = new ArrayList<>();
        if (!baseline.environmentId().equals(migrated.environmentId())) findings.add(finding("PERFORMANCE_ENVIRONMENT_MISMATCH", Domain.PERFORMANCE, Severity.ERROR));
        if (baseline.latencyMillis().size() < 7 || migrated.latencyMillis().size() < 7)
            findings.add(finding("PERFORMANCE_SAMPLE_COUNT_INSUFFICIENT", Domain.PERFORMANCE, Severity.ERROR));
        double noise = Math.max(coefficientOfVariation(baseline.latencyMillis()), coefficientOfVariation(migrated.latencyMillis()));
        if (noise > maximumNoise) findings.add(finding("PERFORMANCE_NOISY_INCONCLUSIVE", Domain.PERFORMANCE, Severity.WARNING));
        else {
            double regression = median(migrated.latencyMillis()) / Math.max(0.000001, median(baseline.latencyMillis())) - 1;
            if (regression >= failThreshold) findings.add(finding("PERFORMANCE_LATENCY_REGRESSION", Domain.PERFORMANCE, Severity.CRITICAL));
            else if (regression >= warningThreshold) findings.add(finding("PERFORMANCE_LATENCY_WARNING", Domain.PERFORMANCE, Severity.WARNING));
        }
        return result(Domain.PERFORMANCE, findings, evidenceRefs);
    }

    public ValidationDecision aggregate(ValidationPolicy policy, Environment baseline, Environment migrated,
                                        List<DomainResult> results, Instant at) {
        Map<Domain,DomainResult> indexed = new EnumMap<>(Domain.class);
        results.forEach(value -> {
            if (indexed.put(value.domain(), value) != null) {
                throw new IllegalArgumentException("duplicate validation domain: " + value.domain());
            }
        });
        List<String> blockers = new ArrayList<>();
        for (Domain required : policy.requiredDomains()) {
            DomainResult result = indexed.get(required);
            if (result == null || result.status() == Status.MISSING || result.status() == Status.INCONCLUSIVE
                    || result.evidenceRefs().isEmpty())
                blockers.add("VALIDATION_EVIDENCE_MISSING:" + required);
            else if (result.status() == Status.FAIL) blockers.add("VALIDATION_DOMAIN_FAILED:" + required);
            else if (result.confidence() < policy.minimumConfidence()) blockers.add("VALIDATION_CONFIDENCE_LOW:" + required);
        }
        for (DomainResult result : results) for (Finding finding : result.findings()) {
            if (finding.severity() == Severity.CRITICAL || policy.hardFailCodes().contains(finding.code())) blockers.add(finding.code());
        }
        Status status = blockers.isEmpty()
                ? results.stream().anyMatch(value -> value.status() == Status.PASS_WITH_WARNINGS) ? Status.PASS_WITH_WARNINGS : Status.PASS
                : Status.FAIL;
        double confidence = results.isEmpty() ? 0 : results.stream().mapToDouble(DomainResult::confidence).average().orElse(0);
        String seed = policy.version() + "\n" + baseline.environmentId() + "\n" + migrated.environmentId() + "\n" + results + "\n" + blockers;
        List<String> refs = results.stream().flatMap(value -> value.evidenceRefs().stream()).distinct().sorted().toList();
        return new ValidationDecision("1.0", "validation-" + hash(seed).substring(0, 24), policy.version(),
                baseline.environmentId(), migrated.environmentId(), status, results, blockers, confidence, at, refs);
    }

    private static DomainResult result(Domain domain, List<Finding> findings, List<String> evidence) {
        List<String> refs = evidence == null ? List.of() : evidence.stream().filter(Objects::nonNull)
                .filter(value -> !value.isBlank()).distinct().sorted().toList();
        boolean failed = findings.stream().anyMatch(value -> value.severity() == Severity.ERROR || value.severity() == Severity.CRITICAL);
        Status status = failed ? Status.FAIL : refs.isEmpty() ? Status.INCONCLUSIVE
                : findings.stream().anyMatch(value -> value.severity() == Severity.WARNING) ? Status.PASS_WITH_WARNINGS : Status.PASS;
        return new DomainResult(domain, status, findings, refs, refs.isEmpty() ? 0 : 1.0);
    }
    private static Finding finding(String code, Domain domain, Severity severity) {
        return new Finding(code, domain, severity, code.replace('_', ' '), List.of());
    }
    private static Map<String,TestCase> indexTests(List<TestCase> values) {
        Map<String,TestCase> result = new TreeMap<>(); for (TestCase value : values) {
            if (result.put(value.identity(), value) != null) throw new IllegalArgumentException("duplicate test identity: " + value.identity());
        } return result;
    }
    private static <T> Set<T> difference(Set<T> left, Set<T> right) { Set<T> value = new TreeSet<>(left); value.removeAll(right); return value; }
    private static List<String> concat(List<String> a, List<String> b) { List<String> result = new ArrayList<>(a); result.addAll(b); return List.copyOf(result); }
    private static List<String> evidence(String a, String b) { return List.of("environment://" + a, "environment://" + b); }
    private static double median(List<Double> values) { List<Double> copy = new ArrayList<>(values); Collections.sort(copy); int n = copy.size(); return n % 2 == 1 ? copy.get(n/2) : (copy.get(n/2-1)+copy.get(n/2))/2; }
    private static double coefficientOfVariation(List<Double> values) { double mean = values.stream().mapToDouble(Double::doubleValue).average().orElse(0); if (mean == 0) return 0; double variance = values.stream().mapToDouble(value -> Math.pow(value - mean, 2)).average().orElse(0); return Math.sqrt(variance) / mean; }
    private static String hash(String value) { try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8))); } catch (Exception error) { throw new IllegalStateException(error); } }
}
