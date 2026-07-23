package io.elmos.worker;

import io.elmos.validation.IndependentValidationJudge;
import io.elmos.validation.ValidationModels.*;
import org.springframework.http.HttpStatus;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/engine/v1/validation")
final class ValidationController {
    record EnvironmentRequest(Environment baseline, Environment migrated) {
        EnvironmentRequest { required(baseline, "baseline"); required(migrated, "migrated"); }
    }
    record BuildRequest(BuildSnapshot baseline, BuildSnapshot migrated) {
        BuildRequest { required(baseline, "baseline"); required(migrated, "migrated"); }
    }
    record TestRequest(List<TestCase> baseline, List<TestCase> migrated, List<String> evidenceRefs) {
        TestRequest { baseline = copied(baseline, "baseline"); migrated = copied(migrated, "migrated"); evidenceRefs = copied(evidenceRefs, "evidenceRefs"); }
        TestRequest(List<TestCase> baseline, List<TestCase> migrated) { this(baseline, migrated, List.of()); }
    }
    record HttpRequest(HttpContract baseline, HttpContract migrated, List<String> evidenceRefs) {
        HttpRequest { required(baseline, "baseline"); required(migrated, "migrated"); evidenceRefs = copied(evidenceRefs, "evidenceRefs"); }
    }
    record JavaRequest(JavaApi baseline, JavaApi migrated, List<String> evidenceRefs) {
        JavaRequest { required(baseline, "baseline"); required(migrated, "migrated"); evidenceRefs = copied(evidenceRefs, "evidenceRefs"); }
    }
    record SerializationRequest(SerializationContract baseline, SerializationContract migrated, Domain domain,
                                List<String> evidenceRefs) {
        SerializationRequest { required(baseline, "baseline"); required(migrated, "migrated"); required(domain, "domain"); evidenceRefs = copied(evidenceRefs, "evidenceRefs"); }
    }
    record DatabaseRequest(DatabaseSchema baseline, DatabaseSchema migrated, List<String> evidenceRefs) {
        DatabaseRequest { required(baseline, "baseline"); required(migrated, "migrated"); evidenceRefs = copied(evidenceRefs, "evidenceRefs"); }
    }
    record TransactionRequest(List<TransactionObservation> baseline, List<TransactionObservation> migrated,
                              List<String> evidenceRefs) {
        TransactionRequest { baseline = copied(baseline, "baseline"); migrated = copied(migrated, "migrated"); evidenceRefs = copied(evidenceRefs, "evidenceRefs"); }
    }
    record PerformanceRequest(PerformanceSample baseline, PerformanceSample migrated, double warningThreshold,
                              double failThreshold, double maximumNoise, List<String> evidenceRefs) {
        PerformanceRequest {
            required(baseline, "baseline"); required(migrated, "migrated"); evidenceRefs = copied(evidenceRefs, "evidenceRefs");
            if (!Double.isFinite(warningThreshold) || !Double.isFinite(failThreshold) || !Double.isFinite(maximumNoise)
                    || warningThreshold < 0 || failThreshold < warningThreshold || maximumNoise < 0) {
                throw new IllegalArgumentException("performance thresholds are invalid");
            }
        }
    }
    record AggregateRequest(ValidationPolicy policy, Environment baseline, Environment migrated,
                            List<DomainResult> results, Instant decidedAt) {
        AggregateRequest {
            required(policy, "policy"); required(baseline, "baseline"); required(migrated, "migrated");
            results = copied(results, "results"); required(decidedAt, "decidedAt");
        }
    }
    private final IndependentValidationJudge judge = new IndependentValidationJudge();

    @PostMapping("/environments/compare") DomainResult environments(@RequestBody EnvironmentRequest request) { return judge.compareEnvironments(request.baseline(), request.migrated()); }
    @PostMapping("/builds/compare") DomainResult builds(@RequestBody BuildRequest request) { return judge.compareBuild(request.baseline(), request.migrated()); }
    @PostMapping("/tests/compare") DomainResult tests(@RequestBody TestRequest request) { return judge.compareTests(request.baseline(), request.migrated(), request.evidenceRefs()); }
    @PostMapping("/http-contracts/compare") DomainResult http(@RequestBody HttpRequest request) { return judge.compareHttp(request.baseline(), request.migrated(), request.evidenceRefs()); }
    @PostMapping("/java-apis/compare") DomainResult javaApi(@RequestBody JavaRequest request) { return judge.compareJava(request.baseline(), request.migrated(), request.evidenceRefs()); }
    @PostMapping("/serialization/compare") DomainResult serialization(@RequestBody SerializationRequest request) { return judge.compareSerialization(request.baseline(), request.migrated(), request.domain(), request.evidenceRefs()); }
    @PostMapping("/database-schemas/compare") DomainResult database(@RequestBody DatabaseRequest request) { return judge.compareDatabase(request.baseline(), request.migrated(), request.evidenceRefs()); }
    @PostMapping("/transactions/compare") DomainResult transactions(@RequestBody TransactionRequest request) { return judge.compareTransactions(request.baseline(), request.migrated(), request.evidenceRefs()); }
    @PostMapping("/performance/compare") DomainResult performance(@RequestBody PerformanceRequest request) { return judge.comparePerformance(request.baseline(), request.migrated(), request.warningThreshold(), request.failThreshold(), request.maximumNoise(), request.evidenceRefs()); }
    @PostMapping("/decisions") ValidationDecision aggregate(@RequestBody AggregateRequest request) { return judge.aggregate(request.policy(), request.baseline(), request.migrated(), request.results(), request.decidedAt()); }

    @ExceptionHandler({IllegalArgumentException.class, HttpMessageNotReadableException.class})
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    Map<String, Object> invalidRequest(Exception ignored) {
        return Map.of(
                "errorCode", "VALIDATION_REQUEST_INVALID",
                "message", "The validation request is malformed or violates the comparison contract.",
                "retryable", false);
    }

    private static <T> T required(T value, String field) {
        if (value == null) throw new IllegalArgumentException(field + " is required");
        return value;
    }

    private static <T> List<T> copied(List<T> values, String field) {
        required(values, field);
        if (values.stream().anyMatch(java.util.Objects::isNull)) {
            throw new IllegalArgumentException(field + " contains null entries");
        }
        return List.copyOf(values);
    }
}
