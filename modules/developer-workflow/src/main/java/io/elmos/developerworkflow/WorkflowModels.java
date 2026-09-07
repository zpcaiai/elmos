package io.elmos.developerworkflow;

import java.util.List;
import java.util.Map;
import java.util.Set;

public final class WorkflowModels {
    private WorkflowModels() {}

    public enum Decision { ALLOW, DENY, ESCALATE }
    public enum Ownership { GENERATED, HUMAN, SHARED }

    public record PolicyDecision(Decision decision, String code, List<String> evidence) {
        public PolicyDecision {
            evidence = List.copyOf(evidence);
        }
        public static PolicyDecision allow(String code, String evidence) {
            return new PolicyDecision(Decision.ALLOW, code, List.of(evidence));
        }
        public static PolicyDecision deny(String code) {
            return new PolicyDecision(Decision.DENY, code, List.of());
        }
        public static PolicyDecision escalate(String code, String evidence) {
            return new PolicyDecision(Decision.ESCALATE, code, List.of(evidence));
        }
    }

    public record ProtocolRequest(
            String protocolVersion,
            String tenantId,
            String projectId,
            String method,
            String workspaceRelativePath,
            String tool,
            Set<String> permissions,
            long documentVersion,
            String artifactDigest) {
        public ProtocolRequest {
            permissions = Set.copyOf(permissions);
        }
    }

    public record SourceNode(
            String nodeId,
            String side,
            String path,
            int startLine,
            int endLine,
            String documentDigest) {}

    public record SourceEdge(
            String from,
            String to,
            String relation,
            double confidence,
            List<String> provenanceRefs) {
        public SourceEdge {
            provenanceRefs = List.copyOf(provenanceRefs);
        }
    }

    public record NavigationResult(Decision decision, String code, List<SourceNode> destinations,
                                   List<String> provenanceRefs) {
        public NavigationResult {
            destinations = List.copyOf(destinations);
            provenanceRefs = List.copyOf(provenanceRefs);
        }
    }

    public record ProtectedRegion(String path, int startLine, int endLine, Ownership ownership,
                                  String owner, boolean approvalRequired) {}

    public record EditRequest(String path, int startLine, int endLine, String actor, boolean approved) {}

    public record PreviewRequest(String sourceDigest, String targetDigest, String recipeDigest,
                                 String environmentDigest, String before, String after,
                                 boolean repositoryWrite, boolean networkAccess) {}

    public record PreviewResult(Decision decision, String code, String diffDigest,
                                int changedLines, boolean repositoryWritten, List<String> evidence) {
        public PreviewResult {
            evidence = List.copyOf(evidence);
        }
    }

    public record TestSelection(Decision decision, String code, Set<String> tests, List<String> evidence) {
        public TestSelection {
            tests = Set.copyOf(tests);
            evidence = List.copyOf(evidence);
        }
    }

    public record PrBotRequest(String provider, String action, Set<String> tokenScopes,
                               String author, String actor, boolean fork, boolean secretsAvailable,
                               String commitDigest, boolean signedEvent, boolean replayedEvent) {
        public PrBotRequest {
            tokenScopes = Set.copyOf(tokenScopes);
        }
    }

    public record Approval(String author, String reviewer, String commitDigest, String artifactDigest,
                           long expiresAtEpochSecond, boolean independent) {}

    public record OfflineBundle(String bundleDigest, String expectedDigest, String trustRoot,
                                Set<String> trustedRoots, Set<String> requestedPermissions,
                                Set<String> grantedPermissions, boolean signed, boolean networkEnabled) {
        public OfflineBundle {
            trustedRoots = Set.copyOf(trustedRoots);
            requestedPermissions = Set.copyOf(requestedPermissions);
            grantedPermissions = Set.copyOf(grantedPermissions);
        }
    }

    public record TelemetryResult(Decision decision, String code, Map<String, String> acceptedFields) {
        public TelemetryResult {
            acceptedFields = Map.copyOf(acceptedFields);
        }
    }
}
