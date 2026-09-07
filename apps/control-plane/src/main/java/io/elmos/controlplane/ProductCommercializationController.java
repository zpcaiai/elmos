package io.elmos.controlplane;

import io.elmos.product.assurance.EvidenceAssuranceModels;
import io.elmos.product.assurance.EvidenceAssuranceService;
import io.elmos.product.execution.SecureExecutionAdmissionService;
import io.elmos.product.execution.SecureExecutionModels;
import io.elmos.product.policy.ContinuousAuthorizationModels;
import io.elmos.product.policy.ContinuousAuthorizationService;
import io.elmos.product.scmworkspace.ScmWorkspaceAdmissionService;
import io.elmos.product.scmworkspace.ScmWorkspaceModels;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/** Product Batch 35-38 readiness APIs. Migration Pack M35-M38 has a separate namespace and gate. */
@RestController
@RequestMapping("/api/v1/product-commercialization")
public final class ProductCommercializationController {
    private final ScmWorkspaceAdmissionService scm = new ScmWorkspaceAdmissionService();
    private final SecureExecutionAdmissionService execution = new SecureExecutionAdmissionService();
    private final EvidenceAssuranceService assurance = new EvidenceAssuranceService();
    private final ContinuousAuthorizationService policy = new ContinuousAuthorizationService();

    @GetMapping("/capabilities")
    public Map<String, Object> capabilities() {
        return Map.of(
                "namespace", "Product Batch B35-B38",
                "migrationPackNamespace", "Migration Pack M35-M45",
                "domains", List.of(
                        Map.of("batch", "B35", "domain", "SCM_AND_ADVANCED_WORKSPACE", "skillCount", 28),
                        Map.of("batch", "B36", "domain", "RUNNER_SANDBOX_EXECUTION_OPERATIONS", "skillCount", 41),
                        Map.of("batch", "B37", "domain", "EVIDENCE_FABRIC_PRODUCERS_ASSURANCE", "skillCount", 48),
                        Map.of("batch", "B38A", "domain", "POLICY_AND_CONTINUOUS_AUTHORIZATION", "skillCount", 16)),
                "decisionCeiling", "READY_FOR_EXTERNAL_GATE_OR_HUMAN_DECISION",
                "externalExecutionEvidence", "NOT_RUN");
    }

    @PostMapping("/B35/admission/evaluate")
    public ScmWorkspaceModels.AdmissionResult evaluateScm(@RequestBody ScmWorkspaceModels.AdmissionRequest request) {
        return scm.evaluate(request);
    }

    @PostMapping("/B36/admission/evaluate")
    public SecureExecutionModels.AdmissionResult evaluateExecution(@RequestBody SecureExecutionModels.AdmissionRequest request) {
        return execution.evaluate(request);
    }

    @PostMapping("/B37/admission/evaluate")
    public EvidenceAssuranceModels.AdmissionResult evaluateAssurance(@RequestBody EvidenceAssuranceModels.AdmissionRequest request) {
        return assurance.evaluate(request);
    }

    @PostMapping("/B38A/decision/evaluate")
    public ContinuousAuthorizationModels.DecisionResult evaluatePolicy(@RequestBody ContinuousAuthorizationModels.DecisionRequest request) {
        return policy.evaluate(request);
    }

    @ExceptionHandler(IllegalArgumentException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    Map<String, Object> badRequest(IllegalArgumentException error) {
        return Map.of("errorCode", "PRODUCT_COMMERCIALIZATION_ADMISSION_REJECTED",
                "message", "The product commercialization request was rejected by its contract.", "retryable", false);
    }
}
