package io.elmos.proofloop;

import com.fasterxml.jackson.databind.MapperFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;

import java.security.MessageDigest;
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static io.elmos.proofloop.ProofLoopModels.Artifact;
import static io.elmos.proofloop.ProofLoopModels.CertificateLevel;
import static io.elmos.proofloop.ProofLoopModels.ExecutionRequest;
import static io.elmos.proofloop.ProofLoopModels.PlanResult;
import static io.elmos.proofloop.ProofLoopModels.RunState;
import static io.elmos.proofloop.ProofLoopModels.SkillResult;

/** Executes the immutable Skill DAG and emits content-addressed, replayable decision receipts. */
public final class ModernizationProofLoopEngine {
    private final SkillContractCatalog catalog;
    private final ProofLoopOperators operators;
    private final ObjectMapper mapper;
    private final Clock clock;

    public ModernizationProofLoopEngine() {
        this(new SkillContractCatalog(), new ProofLoopOperators(), new ObjectMapper(), Clock.systemUTC());
    }

    public ModernizationProofLoopEngine(
            SkillContractCatalog catalog,
            ProofLoopOperators operators,
            ObjectMapper mapper,
            Clock clock
    ) {
        this.catalog = ProofLoopModels.required(catalog, "catalog");
        this.operators = ProofLoopModels.required(operators, "operators");
        this.mapper = ProofLoopModels.required(mapper, "mapper").copy()
                .findAndRegisterModules()
                .configure(MapperFeature.SORT_PROPERTIES_ALPHABETICALLY, true)
                .configure(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS, true)
                .configure(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS, false);
        this.clock = ProofLoopModels.required(clock, "clock");
    }

    public SkillContractCatalog catalog() { return catalog; }

    public PlanResult execute(String targetSkillId, ExecutionRequest template) {
        if (!targetSkillId.equals(template.skillId())) {
            throw new IllegalArgumentException("template skillId must equal targetSkillId");
        }
        List<SkillResult> results = new ArrayList<>();
        Map<String, SkillResult> bySkill = new LinkedHashMap<>();
        String subjectDigest = digest(template.subject());

        for (SkillContractCatalog.Contract contract : catalog.plan(targetSkillId)) {
            Instant startedAt = clock.instant();
            ExecutionRequest request = new ExecutionRequest(
                    template.runId(), compactRequestId(template.runId(), contract.id()), contract.id(), template.actorId(),
                    template.subject(), template.requestedAt(), template.inputs(), template.evidence());

            List<String> dependencyBlockers = localDependencyBlockers(contract, bySkill);
            List<String> subjectBlockers = evidenceSubjectBlockers(request, subjectDigest);
            ProofLoopOperators.OperationOutcome outcome;
            if (!dependencyBlockers.isEmpty() || !subjectBlockers.isEmpty()) {
                List<String> blockers = new ArrayList<>(dependencyBlockers);
                blockers.addAll(subjectBlockers);
                outcome = new ProofLoopOperators.OperationOutcome(
                        RunState.BLOCKED,
                        List.of("contract_validated", "dependency_gate_applied", "fail_closed"),
                        blockers,
                        Map.of("decision", "BLOCKED", "blockers", List.copyOf(blockers)),
                        CertificateLevel.NONE);
            } else {
                outcome = operators.evaluate(contract, request, clock.instant());
            }

            String requestDigest = digest(request);
            Map<String, Object> receiptContent = new LinkedHashMap<>();
            receiptContent.put("schemaVersion", 1);
            receiptContent.put("contractId", contract.id());
            receiptContent.put("contractDigest", contract.canonicalSha256());
            receiptContent.put("runId", request.runId());
            receiptContent.put("requestId", request.requestId());
            receiptContent.put("requestDigest", requestDigest);
            receiptContent.put("subjectDigest", subjectDigest);
            receiptContent.put("decision", outcome.state().name());
            receiptContent.put("claims", outcome.claims());
            receiptContent.put("findings", outcome.findings());
            receiptContent.put("declaredEvidenceSlots", contract.evidence());
            receiptContent.put("referencedEvidence", referencedEvidence(request));
            receiptContent.put("operatorPayload", outcome.payload());
            receiptContent.put("externalOperationExecuted", false);
            receiptContent.put("certified", false);

            Instant finishedAt = clock.instant();
            Artifact receipt = artifact(
                    "decisions/" + contract.id() + ".json", contract.id(), subjectDigest, finishedAt, receiptContent);
            Map<String, Object> resultProjection = new LinkedHashMap<>();
            resultProjection.put("requestDigest", requestDigest);
            resultProjection.put("contractDigest", contract.canonicalSha256());
            resultProjection.put("state", outcome.state().name());
            resultProjection.put("claims", outcome.claims());
            resultProjection.put("findings", outcome.findings());
            resultProjection.put("artifactDigests", List.of(receipt.sha256()));
            resultProjection.put("certificateLevel", outcome.certificateLevel().name());
            String resultDigest = digest(resultProjection);

            SkillResult result = new SkillResult(
                    request.runId(), request.requestId(), contract.id(), contract.name(), contract.batch(), outcome.state(),
                    outcome.claims(), outcome.findings(), List.of(receipt), requestDigest, resultDigest,
                    startedAt, finishedAt, false, false, outcome.certificateLevel());
            results.add(result);
            bySkill.put(contract.id(), result);
        }

        RunState state = aggregateState(results);
        List<String> blockers = results.stream()
                .flatMap(result -> result.findings().stream().map(finding -> result.skillId() + ":" + finding))
                .distinct().sorted().toList();
        CertificateLevel highest = results.stream().map(SkillResult::certificateLevel)
                .max(Comparator.comparingInt(Enum::ordinal)).orElse(CertificateLevel.NONE);
        String planId = "plan:" + digest(Map.of(
                "runId", template.runId(), "target", targetSkillId, "steps",
                results.stream().map(SkillResult::resultDigest).toList())).substring(7, 31);
        return new PlanResult(planId, targetSkillId, results, state, blockers, highest, false, false);
    }

    private List<String> localDependencyBlockers(
            SkillContractCatalog.Contract contract,
            Map<String, SkillResult> results
    ) {
        List<String> blockers = new ArrayList<>();
        for (String dependency : contract.dependencies()) {
            SkillResult result = results.get(dependency);
            if (result != null && result.state() != RunState.PASSED) {
                blockers.add("dependency_not_passed:" + dependency);
            }
        }
        return blockers;
    }

    private List<String> evidenceSubjectBlockers(ExecutionRequest request, String subjectDigest) {
        return request.evidence().entrySet().stream()
                .filter(entry -> !entry.getValue().subjectDigest().equals(subjectDigest))
                .map(entry -> "evidence_subject_mismatch:" + entry.getKey())
                .sorted().toList();
    }

    private List<Map<String, Object>> referencedEvidence(ExecutionRequest request) {
        return request.evidence().entrySet().stream().sorted(Map.Entry.comparingByKey()).map(entry -> {
            Map<String, Object> reference = new LinkedHashMap<>();
            reference.put("key", entry.getKey());
            reference.put("state", entry.getValue().state().name());
            reference.put("subjectDigest", entry.getValue().subjectDigest());
            reference.put("producerId", entry.getValue().producerId());
            reference.put("verifierId", entry.getValue().verifierId());
            reference.put("observedAt", entry.getValue().observedAt().toString());
            reference.put("artifactRefs", entry.getValue().artifactRefs());
            return Map.copyOf(reference);
        }).toList();
    }

    private Artifact artifact(
            String name,
            String producer,
            String subjectDigest,
            Instant createdAt,
            Map<String, Object> content
    ) {
        byte[] bytes = canonicalBytes(content);
        return new Artifact(name, "application/json", sha256(bytes), bytes.length, producer, subjectDigest, createdAt, content);
    }

    private RunState aggregateState(List<SkillResult> results) {
        if (results.stream().anyMatch(result -> result.state() == RunState.FAILED)) return RunState.FAILED;
        if (results.stream().anyMatch(result -> result.state() == RunState.BLOCKED)) return RunState.BLOCKED;
        if (results.stream().anyMatch(result -> result.state() == RunState.PARTIAL)) return RunState.PARTIAL;
        return RunState.PASSED;
    }

    private String compactRequestId(String runId, String skillId) {
        String candidate = runId + ":" + skillId;
        return candidate.length() <= 200 ? candidate : "request:" + digest(candidate).substring(7, 39) + ":" + skillId;
    }

    public String subjectDigest(ProofLoopModels.Subject subject) { return digest(subject); }

    private String digest(Object value) { return sha256(canonicalBytes(value)); }

    private byte[] canonicalBytes(Object value) {
        try { return mapper.writeValueAsBytes(value); }
        catch (Exception exception) { throw new IllegalStateException("cannot canonicalize proof-loop value", exception); }
    }

    private static String sha256(byte[] bytes) {
        try {
            return "sha256:" + HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (Exception exception) {
            throw new IllegalStateException("SHA-256 unavailable", exception);
        }
    }
}
