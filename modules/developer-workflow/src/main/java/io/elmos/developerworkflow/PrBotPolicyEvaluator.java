package io.elmos.developerworkflow;

import java.util.Map;
import java.util.Set;

import static io.elmos.developerworkflow.WorkflowModels.*;

public final class PrBotPolicyEvaluator {
    private static final Map<String,Set<String>> ACTION_SCOPES=Map.of(
            "check",Set.of("contents:read","pull_requests:write"),
            "summarize",Set.of("contents:read","pull_requests:write"),
            "annotate",Set.of("contents:read","checks:write"));

    public PolicyDecision authorize(PrBotRequest request) {
        Set<String> exact=ACTION_SCOPES.get(request.action());
        if (exact==null) return PolicyDecision.deny("BOT_ACTION_NOT_ALLOWLISTED");
        if (!exact.equals(request.tokenScopes())) return PolicyDecision.deny("BOT_SCOPE_NOT_LEAST_PRIVILEGE");
        if (!request.signedEvent() || request.replayedEvent()) return PolicyDecision.deny("SCM_EVENT_UNTRUSTED");
        if (!Digests.exactSha256(request.commitDigest())) return PolicyDecision.deny("EXACT_COMMIT_REQUIRED");
        if (request.author().equals(request.actor()) && request.action().equals("approve")) return PolicyDecision.deny("SELF_APPROVAL_DENIED");
        if (request.fork() && request.secretsAvailable()) return PolicyDecision.deny("FORK_SECRET_ISOLATION_FAILED");
        return PolicyDecision.allow("PR_BOT_ACTION_AUTHORIZED",request.commitDigest());
    }
}
