package io.elmos.agentgateway;

import io.elmos.repair.*;
import io.elmos.repair.RepairModels.*;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/agent/v1")
public final class AgentGatewayController {
    public record NormalizeRequest(RawFailure failure) {}
    public record ClusterRequest(List<Failure> failures) {}
    public record TaskRequest(FailureCluster cluster, RepairScope scope, Risk risk, int maximumAttempts, Instant createdAt) {}
    public record ContextRequest(RepairTask task, List<ContextItem> candidates, int maximumBytes) {}
    public record RouteRequest(RoutingRequest request, List<ProviderProfile> providers) {}
    public record ReserveRequest(RepairBudget budget, String taskId, long estimatedCostMicros, int estimatedInputTokens, int estimatedOutputTokens) {}
    public record ReviewRequest(RepairTask task, AgentPatch patch) {}
    public record LoopRequest(RepairTask task, List<AttemptSnapshot> attempts, VerificationResult verification,
                              long remainingBudgetMicros, List<String> eligibleProviders) {}

    @PostMapping("/failures/normalize") public Failure normalize(@RequestBody NormalizeRequest request) {
        return new FailureNormalizer().normalize(request.failure());
    }
    @PostMapping("/failures/cluster") public List<FailureCluster> cluster(@RequestBody ClusterRequest request) {
        return new FailureNormalizer().cluster(request.failures());
    }
    @PostMapping("/repair-tasks") public RepairTask task(@RequestBody TaskRequest request) {
        return new RepairTaskBuilder().build(request.cluster(), request.scope(), request.risk(), request.maximumAttempts(), request.createdAt());
    }
    @PostMapping("/context-packs") public ContextPack context(@RequestBody ContextRequest request) {
        return new RepairTaskBuilder().pack(request.task(), request.candidates(), request.maximumBytes());
    }
    @PostMapping("/routes") public RoutingDecision route(@RequestBody RouteRequest request) {
        return new AgentRouter().route(request.request(), request.providers());
    }
    @PostMapping("/budgets/reservations") public BudgetReservation reserve(@RequestBody ReserveRequest request) {
        return new BudgetController().reserve(request.budget(), request.taskId(), request.estimatedCostMicros(),
                request.estimatedInputTokens(), request.estimatedOutputTokens());
    }
    @PostMapping("/patch-reviews") public PatchReview review(@RequestBody ReviewRequest request) {
        return new RepairPolicyEngine().review(request.task(), request.patch());
    }
    @PostMapping("/loop-decisions") public LoopDecision loop(@RequestBody LoopRequest request) {
        return new RepairPolicyEngine().next(request.task(), request.attempts(), request.verification(),
                request.remainingBudgetMicros(), request.eligibleProviders());
    }
    @GetMapping("/provider-plans/{provider}") public ProviderCommandPlan providerPlan(@PathVariable ProviderType provider,
                                                                                     @RequestParam String taskFile) {
        return switch (provider) {
            case CODEX -> ProviderPolicies.codex(taskFile);
            case CLAUDE -> ProviderPolicies.claude(taskFile);
            case OPENHANDS -> ProviderPolicies.openHands(taskFile);
            case HUMAN -> throw new IllegalArgumentException("human escalation does not have an executable provider plan");
        };
    }
    @GetMapping("/execution-capability") public Map<String,Object> executionCapability() {
        return Map.of("configured", false, "reasonCode", "AGENT_EXECUTOR_NOT_CONFIGURED",
                "message", "Provider plans are policy artifacts; execution requires an isolated configured runner.");
    }
    @ExceptionHandler({IllegalArgumentException.class, IllegalStateException.class, SecurityException.class})
    @ResponseStatus(HttpStatus.BAD_REQUEST) Map<String,Object> badRequest(RuntimeException error) {
        return Map.of("errorCode", "AGENT_REQUEST_REJECTED", "message", error.getMessage(), "retryable", false);
    }
}
