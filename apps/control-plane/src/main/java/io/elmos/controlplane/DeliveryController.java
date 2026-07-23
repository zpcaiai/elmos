package io.elmos.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.delivery.*;
import io.elmos.delivery.DeliveryModels.*;
import io.elmos.validation.ValidationModels.Status;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/delivery")
public final class DeliveryController {
    public record SnapshotRequest(String migrationId, String sourceSnapshotId, String sourceCommit, String headSha,
                                  String validationDecisionId, Status validationStatus, List<EvidenceFact> facts,
                                  List<RiskItem> risks, String rollbackPlanId, String evidencePackId, Instant createdAt) {}
    public record StaleRequest(DeliverySnapshot snapshot, String currentHeadSha) {}
    public record ScmPlanRequest(ScmProvider provider, String repository, String migrationId, String baseBranch,
                                 String headSha, String title, String body, List<String> reviewers) {}
    public record CheckRequest(ScmProvider provider, GitLabTier tier, String name, String boundHeadSha,
                               String currentHeadSha, CheckConclusion conclusion, List<Annotation> annotations, String summary) {}
    public record RollbackRequest(String migrationId, List<Change> changes, Integer rtoMinutes, Integer rpoMinutes,
                                  DrillStatus drillStatus) {}
    public record AcceptanceRequest(String migrationId, String deliveredHeadSha, String currentHeadSha,
                                    List<AcceptanceCriterion> criteria, List<String> conditions,
                                    boolean merged, boolean released, boolean closureRequested,
                                    String acceptedBy, Instant acceptedAt) {}

    private final DeliveryReadModel readModel; private final ObjectMapper json;
    public DeliveryController(ObjectMapper json) { this.json = json; this.readModel = new DeliveryReadModel(json); }

    @PostMapping("/snapshots") public DeliverySnapshot snapshot(@RequestBody SnapshotRequest request) {
        return readModel.assemble(request.migrationId(), request.sourceSnapshotId(), request.sourceCommit(), request.headSha(),
                request.validationDecisionId(), request.validationStatus(), request.facts(), request.risks(),
                request.rollbackPlanId(), request.evidencePackId(), request.createdAt());
    }
    @PostMapping("/snapshots/stale-check") public DeliverySnapshot stale(@RequestBody StaleRequest request) {
        return readModel.markStale(request.snapshot(), request.currentHeadSha());
    }
    @PostMapping("/reports") public ReportBundle report(@RequestBody DeliverySnapshot snapshot) {
        return new ReportGenerator(json).generate(snapshot);
    }
    @PostMapping("/scm/plans") public ScmDeliveryPlan scmPlan(@RequestBody ScmPlanRequest request) {
        return new ScmDeliveryPolicy().plan(request.provider(), request.repository(), request.migrationId(), request.baseBranch(),
                request.headSha(), request.title(), request.body(), request.reviewers());
    }
    @PostMapping("/scm/checks") public CheckPublication check(@RequestBody CheckRequest request) {
        return new ScmDeliveryPolicy().check(request.provider(), request.tier(), request.name(), request.boundHeadSha(),
                request.currentHeadSha(), request.conclusion(), request.annotations(), request.summary());
    }
    @PostMapping("/rollback-plans") public RollbackPlan rollback(@RequestBody RollbackRequest request) {
        return new RollbackPlanner().plan(request.migrationId(), request.changes(), request.rtoMinutes(), request.rpoMinutes(), request.drillStatus());
    }
    @PostMapping("/acceptance") public AcceptancePackage acceptance(@RequestBody AcceptanceRequest request) {
        return new AcceptancePolicy().evaluate(request.migrationId(), request.deliveredHeadSha(), request.currentHeadSha(),
                request.criteria(), request.conditions(), request.merged(), request.released(), request.closureRequested(),
                request.acceptedBy(), request.acceptedAt());
    }
    @GetMapping("/evidence-packs/capability") public Map<String,Object> evidencePackCapability() {
        return Map.of("configured", false, "reasonCode", "SIGNING_KEY_NOT_CONFIGURED",
                "message", "Evidence pack signing is fail-closed until an external Ed25519 signing key provider is configured.");
    }
    @ExceptionHandler({IllegalArgumentException.class, IllegalStateException.class, SecurityException.class})
    @ResponseStatus(HttpStatus.BAD_REQUEST) Map<String,Object> badRequest(RuntimeException error) {
        return Map.of("errorCode", "DELIVERY_REQUEST_REJECTED", "message", "The delivery request was rejected by its contract.", "retryable", false);
    }
}
