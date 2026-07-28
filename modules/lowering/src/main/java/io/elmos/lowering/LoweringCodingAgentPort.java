package io.elmos.lowering;

import java.util.List;

/**
 * The real Coding Agent seam for cross-language lowering (Batch 5), per
 * {@code docs/adr/ADR-0059-coding-agent-model-catalog.md}.
 *
 * {@link MethodBodyLoweringService} already produces a {@link LoweringModels.AgentPacket}
 * whenever a callable cannot be lowered deterministically and
 * {@code GenerationProfile.allowAgentFallback()} together with the
 * {@code Budgets.maxAgentCalls()} budget allow it — see the {@code "agent-required"}
 * status on {@link LoweringModels.CallableResult}. Nothing in that service
 * calls a model with the packet today; this port answers a narrower,
 * downstream question given an already-produced packet: which candidate
 * models are actually provisionable right now (real credential present, real
 * health probe passed)? It deliberately does not decide whether to run the
 * lowering pipeline itself, and does not run the full
 * {@code io.elmos.enterprise.PrivateExecutionGovernance.routeModel} policy
 * gate (data classification, secret scan, budget reservation), since this
 * module does not yet produce those inputs for a given packet.
 */
public interface LoweringCodingAgentPort {
    record CandidateModel(String modelId, boolean approved, List<String> reasonCodes) {
        public CandidateModel {
            reasonCodes = List.copyOf(reasonCodes);
        }
    }

    List<CandidateModel> provisionCandidates(String organizationId, LoweringModels.AgentPacket packet);
    boolean configured();
    String configurationReason();
}
