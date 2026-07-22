package io.elmos.worker;

import io.elmos.validation.IndependentValidationJudge;
import io.elmos.validation.ValidationModels.*;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.List;

@RestController
@RequestMapping("/engine/v1/validation")
final class ValidationController {
    record EnvironmentRequest(Environment baseline, Environment migrated) {}
    record BuildRequest(BuildSnapshot baseline, BuildSnapshot migrated) {}
    record TestRequest(List<TestCase> baseline, List<TestCase> migrated, List<String> evidenceRefs) {
        TestRequest(List<TestCase> baseline, List<TestCase> migrated) { this(baseline, migrated, List.of()); }
    }
    record HttpRequest(HttpContract baseline, HttpContract migrated, List<String> evidenceRefs) {}
    record JavaRequest(JavaApi baseline, JavaApi migrated, List<String> evidenceRefs) {}
    record SerializationRequest(SerializationContract baseline, SerializationContract migrated, Domain domain,
                                List<String> evidenceRefs) {}
    record DatabaseRequest(DatabaseSchema baseline, DatabaseSchema migrated, List<String> evidenceRefs) {}
    record TransactionRequest(List<TransactionObservation> baseline, List<TransactionObservation> migrated,
                              List<String> evidenceRefs) {}
    record PerformanceRequest(PerformanceSample baseline, PerformanceSample migrated, double warningThreshold,
                              double failThreshold, double maximumNoise, List<String> evidenceRefs) {}
    record AggregateRequest(ValidationPolicy policy, Environment baseline, Environment migrated,
                            List<DomainResult> results, Instant decidedAt) {}
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
}
