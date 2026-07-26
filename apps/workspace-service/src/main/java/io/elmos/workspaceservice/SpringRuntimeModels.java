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
            List<String> healthCandidates
    ) {
        Request {
            healthCandidates = healthCandidates == null ? List.of() : List.copyOf(healthCandidates);
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
