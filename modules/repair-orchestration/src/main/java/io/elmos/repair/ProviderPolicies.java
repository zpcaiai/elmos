package io.elmos.repair;

import io.elmos.repair.RepairModels.*;

import java.util.List;
import java.util.Map;
import java.util.Set;

public final class ProviderPolicies {
    private ProviderPolicies() {}

    public static ProviderCommandPlan codex(String taskFile) {
        return new ProviderCommandPlan(ProviderType.CODEX,
                List.of("codex", "exec", "--sandbox", "workspace-write", "--ask-for-approval", "never", "--json", "-"),
                Map.of("ELMOS_TASK_FILE", taskFile), Set.of("danger-full-access", "interactive-approval", "git-push", "docker-socket"),
                false, false);
    }

    public static ProviderCommandPlan claude(String taskFile) {
        return new ProviderCommandPlan(ProviderType.CLAUDE,
                List.of("claude", "--print", "--output-format", "json", "--permission-mode", "dontAsk"),
                Map.of("ELMOS_TASK_FILE", taskFile, "ELMOS_PRETOOL_HOOK", "deny-network-git-docker-secrets"),
                Set.of("network", "git-push", "docker-socket", "secret-read", "validation-workspace"), false, false);
    }

    public static ProviderCommandPlan openHands(String taskFile) {
        return new ProviderCommandPlan(ProviderType.OPENHANDS,
                List.of("openhands", "agent-server", "--workspace", "/workspace/edit", "--task-file", taskFile),
                Map.of("SANDBOX_RUNTIME", "rootless-container", "NETWORK_POLICY", "deny"),
                Set.of("host-docker-socket", "privileged", "host-network", "git-push", "validation-workspace"), false, false);
    }
}
