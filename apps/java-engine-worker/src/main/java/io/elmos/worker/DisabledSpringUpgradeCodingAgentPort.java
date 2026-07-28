package io.elmos.worker;

import java.util.List;

import static io.elmos.worker.SpringUpgradeModels.*;

final class DisabledSpringUpgradeCodingAgentPort implements SpringUpgradeCodingAgentPort {
    private final String reason;

    DisabledSpringUpgradeCodingAgentPort(String reason) {
        this.reason = reason;
    }

    @Override
    public List<CandidateModel> provisionCandidates(String organizationId, String runId) {
        throw new BlockedException("CODING_AGENT_NOT_CONFIGURED", reason);
    }

    @Override public boolean configured() { return false; }
    @Override public String configurationReason() { return reason; }
}
