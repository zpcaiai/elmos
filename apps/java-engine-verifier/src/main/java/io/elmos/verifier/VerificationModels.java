package io.elmos.verifier;

import java.time.Instant;
import java.util.List;

final class VerificationModels {
    private VerificationModels() {}

    record Request(
            String runId,
            String artifactRelativePath,
            String artifactSha256,
            String targetSpringBoot,
            String targetJava
    ) {
        Request {
            if (targetSpringBoot == null || targetSpringBoot.isBlank()) targetSpringBoot = "3.5.3";
            if (targetJava == null || targetJava.isBlank()) targetJava = "21";
        }

        Request(String runId, String artifactRelativePath, String artifactSha256) {
            this(runId, artifactRelativePath, artifactSha256, "3.5.3", "21");
        }
    }

    record Response(
            String status,
            String verifierId,
            String artifactSha256,
            String targetSpringBoot,
            String targetJava,
            boolean freshArtifactWorkspace,
            boolean transformCapability,
            boolean physicallySeparateVerifierService,
            String evidenceRelativePath,
            String logRelativePath,
            String evidenceSha256,
            long evidenceBytes,
            String logSha256,
            long logBytes,
            String runtimeArtifactRelativePath,
            String runtimeArtifactSha256,
            long runtimeArtifactBytes,
            List<String> command,
            Instant decidedAt
    ) {
        Response {
            command = List.copyOf(command);
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
