package io.elmos.lowering;

import java.util.List;

public final class DisabledLoweringCodingAgentPort implements LoweringCodingAgentPort {
    private final String reason;

    public DisabledLoweringCodingAgentPort(String reason) {
        this.reason = reason;
    }

    @Override
    public List<CandidateModel> provisionCandidates(String organizationId, LoweringModels.AgentPacket packet) {
        throw new IllegalStateException("LOWERING_CODING_AGENT_NOT_CONFIGURED: " + reason);
    }

    @Override public boolean configured() { return false; }
    @Override public String configurationReason() { return reason; }
}
