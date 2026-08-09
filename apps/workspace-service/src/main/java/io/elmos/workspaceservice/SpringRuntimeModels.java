package io.elmos.workspaceservice;

import java.util.List;

final class SpringRuntimeModels {
    private SpringRuntimeModels() {}

    enum Action { START, STOP, LOGS }

    record Request(
            Action action,
            String runtimeId,
            String organizationId,
            String artifactRelativePath,
            String artifactSha256,
            List<String> healthCandidates,
            String targetJava
    ) {
        Request {
            healthCandidates = healthCandidates == null ? List.of() : List.copyOf(healthCandidates);
            if (action == Action.START && (targetJava == null || targetJava.isBlank())) {
                // Rolling compatibility for the original single-target 3.5.3 / Java 21 protocol.
                targetJava = "21";
            }
        }

        Request(
                Action action,
                String runtimeId,
                String organizationId,
                String artifactRelativePath,
                String artifactSha256,
                List<String> healthCandidates
        ) {
            this(action, runtimeId, organizationId, artifactRelativePath, artifactSha256,
                    healthCandidates, action == Action.START ? "21" : null);
        }
    }

    record Response(
            String status,
            String runtimeId,
            String imageDigest,
            int port,
            String healthPath,
            List<String> logs,
            boolean logsTruncated
    ) {
        Response {
            logs = List.copyOf(logs);
        }
    }

    static final class Rejected extends RuntimeException {
        private final String code;
        Rejected(String code, String message) {
            super(message);
            this.code = code;
        }
        String code() { return code; }
    }
}
