package io.elmos.worker;

import java.util.List;

/**
 * The "Coding Agent 只处理验证后的长尾问题" seam described in the root README and
 * {@code docs/adr/ADR-0059-coding-agent-model-catalog.md}. Today nothing in
 * {@link LocalSpringUpgradeExecutionPort} calls this port yet — the pipeline's
 * only real long-tail behavior is {@code Stage.DETERMINISTIC_REPAIR}, which
 * re-runs the same pinned OpenRewrite recipe once. This port exists so that
 * decision can be made deliberately, with the pipeline's one route with real
 * end-to-end local execution evidence (Boot 2.7.18 / Java 17) left untouched
 * until that follow-up change can itself be compiled and tested.
 *
 * <p>This port intentionally answers a narrower question than
 * {@code io.elmos.enterprise.PrivateExecutionGovernance.routeModel}: it only
 * reports which candidate models are actually provisionable right now
 * (credential present and health probe passed). It does not run the full
 * {@code ModelPolicy} gate (data classification, secret scan, budget
 * reservation) because this pipeline does not yet produce those inputs —
 * doing so with placeholder values would look like a real policy decision
 * while actually being hard-wired to always block. Whoever adds a real
 * secret-scan / budget step to this pipeline should call {@code routeModel}
 * directly with the real values at that point, using the endpoints this port
 * provisions.
 */
interface SpringUpgradeCodingAgentPort {
    record CandidateModel(String modelId, boolean approved, List<String> reasonCodes) {
        public CandidateModel {
            reasonCodes = List.copyOf(reasonCodes);
        }
    }

    List<CandidateModel> provisionCandidates(String organizationId, String runId);
    boolean configured();
    String configurationReason();
}
