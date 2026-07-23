package io.elmos.commercialapi;

import io.elmos.commercial.*;
import io.elmos.commercial.CommercialModels.*;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/commercial/v1")
public final class CommercialController {
    private final EntitlementAndFulfillmentService entitlement = new EntitlementAndFulfillmentService();
    private final OnboardingAndProjectService project = new OnboardingAndProjectService();
    private final SlaAndSupportService support = new SlaAndSupportService();
    private final AssetAndKnowledgeGovernance assets = new AssetAndKnowledgeGovernance();
    private final CustomerSuccessAndAnalyticsService success = new CustomerSuccessAndAnalyticsService();

    public record EntitlementRequest(String organizationId, String featureKey, List<Entitlement> entitlements,
                                     BigDecimal requested, boolean securityRestricted, boolean contractRestricted,
                                     String policyVersion, Instant now) {}
    public record ReadinessRequest(String organizationId, String deploymentMode, List<ReadinessDimension> dimensions) {}
    public record ProjectRequest(String projectId, List<ProjectStep> steps, Instant p50, Instant p80,
                                 BigDecimal budgetUsed, BigDecimal budgetLimit, boolean overrideRequested,
                                 String overrideReason) {}
    public record SlaRequest(ServiceLevelObjective objective, ServiceLevelMeasurement measurement,
                             boolean exclusionContractuallyAllowed, BigDecimal creditRate, BigDecimal maximumCredit) {}
    public record TriageRequest(String ticketId, String type, TicketContext context, boolean multiCustomerOutage,
                                boolean evidenceIntegrityRisk, boolean suspectedDataExposure,
                                boolean enterpriseCriticalBlock, boolean workaroundAvailable,
                                String impact, String urgency, List<String> fingerprints) {}
    public record ListingRequest(RecipeAsset asset, AssetVisibility visibility,
                                 boolean testsPassed, boolean canaryPassed, boolean maintainerAssigned) {}
    public record KnowledgeRequest(KnowledgeArticle article, String requestingOrganizationId,
                                   boolean versionCompatible, boolean sourceStillApproved) {}

    @PostMapping("/entitlements/decide") EntitlementDecision entitlement(@RequestBody EntitlementRequest request) {
        return entitlement.decide(request.organizationId(), request.featureKey(), request.entitlements(), request.requested(),
                request.securityRestricted(), request.contractRestricted(), request.policyVersion(), request.now());
    }
    @PostMapping("/orders/fulfill") FulfillmentResult fulfill(@RequestBody CommercialOrder order) {
        return entitlement.fulfill(order, Instant.now());
    }
    @PostMapping("/onboarding/readiness") OnboardingReadiness readiness(@RequestBody ReadinessRequest request) {
        return project.assessReadiness(request.organizationId(), request.deploymentMode(), request.dimensions());
    }
    @PostMapping("/projects/status") ProjectStatusSnapshot project(@RequestBody ProjectRequest request) {
        return project.projectStatus(request.projectId(), request.steps(), request.p50(), request.p80(),
                request.budgetUsed(), request.budgetLimit(), request.overrideRequested(), request.overrideReason());
    }
    @PostMapping("/sla/evaluate") ServiceLevelDecision sla(@RequestBody SlaRequest request) {
        return support.evaluate(request.objective(), request.measurement(), request.exclusionContractuallyAllowed(),
                request.creditRate(), request.maximumCredit());
    }
    @PostMapping("/support/triage") SupportTicket triage(@RequestBody TriageRequest request) {
        return support.triage(request.ticketId(), request.type(), request.context(), request.multiCustomerOutage(),
                request.evidenceIntegrityRisk(), request.suspectedDataExposure(), request.enterpriseCriticalBlock(),
                request.workaroundAvailable(), request.impact(), request.urgency(), request.fingerprints());
    }
    @PostMapping("/assets/listing-decisions") AssetDecision listing(@RequestBody ListingRequest request) {
        return assets.evaluateListing(request.asset(), request.visibility(), request.testsPassed(),
                request.canaryPassed(), request.maintainerAssigned());
    }
    @PostMapping("/knowledge/decisions") KnowledgeDecision knowledge(@RequestBody KnowledgeRequest request) {
        return assets.evaluateKnowledge(request.article(), request.requestingOrganizationId(),
                request.versionCompatible(), request.sourceStillApproved());
    }
    @PostMapping("/customer-success/health") CustomerHealth health(@RequestBody CustomerSignals signals) {
        return success.health(signals);
    }
    @GetMapping("/capabilities") Map<String,Object> capabilities() {
        return Map.ofEntries(Map.entry("schemaVersion", "1.0"), Map.entry("entitlement", "AVAILABLE"),
                Map.entry("orderFulfillment", "AVAILABLE"), Map.entry("onboarding", "AVAILABLE"),
                Map.entry("projectCockpit", "AVAILABLE"), Map.entry("sla", "AVAILABLE"),
                Map.entry("support", "AVAILABLE"), Map.entry("marketplacePolicy", "AVAILABLE"),
                Map.entry("knowledgePolicy", "AVAILABLE"), Map.entry("externalCrm", "NOT_CONFIGURED"),
                Map.entry("paymentStatus", "NOT_CONFIGURED"), Map.entry("formalAccounting", "OUT_OF_SCOPE"));
    }
    @ExceptionHandler({IllegalArgumentException.class, IllegalStateException.class, SecurityException.class})
    @ResponseStatus(HttpStatus.BAD_REQUEST) Map<String,Object> bad(RuntimeException error) {
        return Map.of("errorCode", "COMMERCIAL_POLICY_REJECTED", "message", "The commercial request was rejected by its policy contract.", "retryable", false);
    }
}
