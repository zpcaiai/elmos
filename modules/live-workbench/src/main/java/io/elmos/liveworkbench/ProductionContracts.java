package io.elmos.liveworkbench;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static io.elmos.liveworkbench.LwContracts.*;

/** Public production control-plane contracts. Tenant and actor fields are never accepted from request bodies. */
public final class ProductionContracts {
    private ProductionContracts() {}

    public record PrincipalScope(String tenantId, String accountId, String actorId, String environmentId,
                                 Set<String> authorities) {
        public PrincipalScope {
            bounded(tenantId, "tenantId", 200); bounded(accountId, "accountId", 200);
            bounded(actorId, "actorId", 200); bounded(environmentId, "environmentId", 200);
            authorities = Set.copyOf(authorities == null ? Set.of() : authorities);
        }
        public boolean has(String authority) { return authorities.contains(authority); }
    }

    public record CreateSessionRequest(String deliveryId, String repositoryId, String snapshotId,
                                       String runtimeProfileId, String scenario, String mode,
                                       int slotWeight, boolean debugRequired) {
        public CreateSessionRequest {
            bounded(deliveryId, "deliveryId", 200); bounded(repositoryId, "repositoryId", 200);
            requireDigest(snapshotId, "snapshotId"); bounded(runtimeProfileId, "runtimeProfileId", 200);
            bounded(scenario, "scenario", 500);
            if (!Set.of("run", "debug", "compare", "learn").contains(mode)) throw new IllegalArgumentException("unsupported mode");
            if (slotWeight < 1 || slotWeight > MAX_ACCOUNT_SLOTS) throw new IllegalArgumentException("slotWeight");
            if (debugRequired && !Set.of("debug", "compare", "learn").contains(mode)) throw new IllegalArgumentException("debug requires compatible mode");
        }
    }

    public record ProviderAllocation(String providerSessionId, String resourceLeaseId,
                                     long hardDeadlineEpochSecond, Map<String, String> members,
                                     List<String> evidenceRefs) {
        public ProviderAllocation {
            requireText(providerSessionId, "providerSessionId"); requireText(resourceLeaseId, "resourceLeaseId");
            if (hardDeadlineEpochSecond < 1) throw new IllegalArgumentException("provider hard deadline");
            members = Map.copyOf(members == null ? Map.of() : members);
            evidenceRefs = List.copyOf(evidenceRefs == null ? List.of() : evidenceRefs);
            if (members.size() > 100 || evidenceRefs.size() > 100) throw new IllegalArgumentException("provider evidence bounds");
            if (members.isEmpty() || members.entrySet().stream().anyMatch(entry -> entry.getKey().isBlank() || entry.getValue().isBlank()))
                throw new IllegalArgumentException("provider resource members required");
            if (evidenceRefs.isEmpty()) throw new IllegalArgumentException("provider allocation evidence required");
        }
    }

    public record SessionView(String tenantId, String accountId, String actorId, String sessionId,
                              String deliveryId, String repositoryId, String snapshotId, String runtimeProfileId,
                              String scenario, String mode, int generation, int slotWeight, SessionState state,
                              RuntimeStatus runtimeStatus, long createdAtEpochSecond, Long firstReadyAtEpochSecond,
                              Long expiresAtEpochSecond, long providerHardDeadlineEpochSecond,
                              String providerSessionId, String resourceLeaseId, Map<String, String> resourceMembers,
                              List<String> evidenceRefs, long version) {
        public SessionView {
            requireText(tenantId, "tenantId"); requireText(accountId, "accountId"); requireText(actorId, "actorId");
            requireText(sessionId, "sessionId"); requireText(deliveryId, "deliveryId"); requireText(repositoryId, "repositoryId");
            requireDigest(snapshotId, "snapshotId"); requireText(runtimeProfileId, "runtimeProfileId");
            if (generation < 1 || slotWeight < 1 || state == null || runtimeStatus == null || createdAtEpochSecond < 0 || version < 0)
                throw new IllegalArgumentException("invalid session state");
            resourceMembers = Map.copyOf(resourceMembers == null ? Map.of() : resourceMembers);
            evidenceRefs = List.copyOf(evidenceRefs == null ? List.of() : evidenceRefs);
        }
        public long remainingSeconds(long now) {
            return state == SessionState.READY && expiresAtEpochSecond != null ? Math.max(0, expiresAtEpochSecond - now) : 0;
        }
    }

    public record ReadinessRequest(String artifactDigest, String verifierId, String signatureRef,
                                   long verifiedAtEpochSecond, Map<String, Boolean> checks,
                                   List<String> evidenceRefs) {
        public ReadinessRequest {
            requireDigest(artifactDigest, "artifactDigest"); requireText(verifierId, "verifierId");
            requireText(signatureRef, "signatureRef"); if (verifiedAtEpochSecond < 0) throw new IllegalArgumentException("verifiedAt");
            checks = Map.copyOf(checks == null ? Map.of() : checks);
            evidenceRefs = List.copyOf(evidenceRefs == null ? List.of() : evidenceRefs);
            if (checks.size() > 100 || evidenceRefs.size() > 100) throw new IllegalArgumentException("readiness evidence bounds");
            if (checks.isEmpty() || checks.values().stream().anyMatch(Boolean.FALSE::equals) || evidenceRefs.isEmpty())
                throw new IllegalArgumentException("committed independent readiness evidence required");
        }
    }

    public record DebugRequest(String command, String argumentsDigest, int stopEpoch, String controlLeaseId) {
        public DebugRequest {
            if (!Set.of("continue", "pause", "next", "stepIn", "stepOut", "terminate", "stackTrace", "variables").contains(command))
                throw new IllegalArgumentException("debug command is not allowlisted");
            requireDigest(argumentsDigest, "argumentsDigest"); if (stopEpoch < 0) throw new IllegalArgumentException("stopEpoch");
            requireText(controlLeaseId, "controlLeaseId");
        }
        public boolean sideEffecting() { return Set.of("continue", "pause", "next", "stepIn", "stepOut", "terminate").contains(command); }
    }

    public record DebugReceipt(String commandId, String idempotencyKey, CommandState state,
                               String code, String evidenceRef, long version) {
        public DebugReceipt {
            requireText(commandId, "commandId"); requireText(idempotencyKey, "idempotencyKey");
            if (state == null) throw new IllegalArgumentException("state"); requireText(code, "code");
        }
    }

    public record ProviderCommandResult(CommandState state, String evidenceRef, String responseDigest) {
        public ProviderCommandResult {
            if (state != CommandState.COMMITTED && state != CommandState.UNKNOWN && state != CommandState.DENIED)
                throw new IllegalArgumentException("provider command state");
            if (responseDigest != null) requireDigest(responseDigest, "responseDigest");
        }
    }

    public record RuntimeEventRequest(String eventId, int generation, int stopEpoch, long sequence,
                                      String kind, String payloadDigest, List<String> sourceAnchorIds,
                                      String redactionStatus, long serverTimeEpochSecond) {
        public RuntimeEventRequest {
            requireText(eventId, "eventId"); if (generation < 1 || stopEpoch < 0 || sequence < 1) throw new IllegalArgumentException("event ordering");
            requireText(kind, "kind"); requireDigest(payloadDigest, "payloadDigest");
            sourceAnchorIds = List.copyOf(sourceAnchorIds == null ? List.of() : sourceAnchorIds);
            if (sourceAnchorIds.size() > 100) throw new IllegalArgumentException("source anchor bound");
            if (!Set.of("none-needed", "redacted", "omitted").contains(redactionStatus)) throw new IllegalArgumentException("redactionStatus");
            if (serverTimeEpochSecond < 0) throw new IllegalArgumentException("serverTime");
        }
    }

    public record EventView(String eventId, String sessionId, int generation, int stopEpoch, long sequence,
                            String kind, String payloadDigest, List<String> sourceAnchorIds,
                            String redactionStatus, long serverTimeEpochSecond) {
        public EventView { sourceAnchorIds = List.copyOf(sourceAnchorIds); }
    }

    public record ExplanationRequest(String anchorId, String audience, String mode) {
        public ExplanationRequest {
            requireText(anchorId, "anchorId"); requireText(audience, "audience");
            if (!Set.of("line", "module", "architecture").contains(mode)) throw new IllegalArgumentException("explanation mode");
        }
    }

    public record ExplanationView(SourceAnchor anchor, String audience, String mode,
                                  List<EvidenceClaim> claims, List<String> limitations) {
        public ExplanationView {
            if (anchor == null) throw new IllegalArgumentException("anchor");
            claims = List.copyOf(claims == null ? List.of() : claims);
            limitations = List.copyOf(limitations == null ? List.of() : limitations);
        }
    }

    public record SourceContent(SourceAnchor anchor, String content, String selectionDigest,
                                List<String> evidenceRefs) {
        public SourceContent {
            if (anchor == null) throw new IllegalArgumentException("anchor"); requireText(content, "content");
            requireDigest(selectionDigest, "selectionDigest");
            if (content.getBytes(java.nio.charset.StandardCharsets.UTF_8).length > 1_048_576)
                throw new IllegalArgumentException("source selection too large");
            if (!LwDigest.sha256(content.getBytes(java.nio.charset.StandardCharsets.UTF_8)).equals(selectionDigest))
                throw new IllegalArgumentException("source selection digest mismatch");
            if (content.getBytes(java.nio.charset.StandardCharsets.UTF_8).length != anchor.byteEnd() - anchor.byteStart())
                throw new IllegalArgumentException("source selection byte range mismatch");
            evidenceRefs = List.copyOf(evidenceRefs == null ? List.of() : evidenceRefs);
            if (evidenceRefs.isEmpty()) throw new IllegalArgumentException("source evidence required");
        }
    }

    public record MissionAttemptRequest(String sessionId, int generation, String answersDigest,
                                        List<String> runtimeEventIds) {
        public MissionAttemptRequest {
            requireText(sessionId, "sessionId"); if (generation < 1) throw new IllegalArgumentException("generation");
            requireDigest(answersDigest, "answersDigest");
            runtimeEventIds = List.copyOf(runtimeEventIds == null ? List.of() : runtimeEventIds);
            if (runtimeEventIds.isEmpty() || runtimeEventIds.size() > 500) throw new IllegalArgumentException("server runtime evidence required");
        }
    }

    public record MissionAttemptReceipt(String attemptId, String idempotencyKey, CommandState state,
                                        Integer score, List<String> feedbackClaimIds,
                                        List<String> evidenceRefs, long version) {
        public MissionAttemptReceipt {
            requireText(attemptId, "attemptId"); requireText(idempotencyKey, "idempotencyKey");
            if (state == null || version < 0) throw new IllegalArgumentException("attempt state");
            if (score != null && (score < 0 || score > 100)) throw new IllegalArgumentException("score");
            feedbackClaimIds = List.copyOf(feedbackClaimIds == null ? List.of() : feedbackClaimIds);
            evidenceRefs = List.copyOf(evidenceRefs == null ? List.of() : evidenceRefs);
            if (state == CommandState.COMMITTED && (score == null || evidenceRefs.isEmpty()))
                throw new IllegalArgumentException("committed assessment evidence required");
        }
    }

    public record CleanupOutcome(SessionState status, Map<String, Boolean> memberChecks,
                                 String verifierId, List<String> evidenceRefs, long observedAtEpochSecond) {
        public CleanupOutcome {
            if (status != SessionState.CLEANED && status != SessionState.QUARANTINED) throw new IllegalArgumentException("cleanup status");
            memberChecks = Map.copyOf(memberChecks == null ? Map.of() : memberChecks);
            requireText(verifierId, "verifierId"); evidenceRefs = List.copyOf(evidenceRefs == null ? List.of() : evidenceRefs);
            if (memberChecks.isEmpty() || evidenceRefs.isEmpty()) throw new IllegalArgumentException("cleanup evidence required");
            if (status == SessionState.CLEANED && memberChecks.values().stream().anyMatch(value -> !value))
                throw new IllegalArgumentException("cleaned status requires every resource check");
            if (observedAtEpochSecond < 0) throw new IllegalArgumentException("observedAt");
        }
    }

    public record ApiSession(SessionView session, long serverNowEpochSecond, long remainingSeconds,
                             String schemaVersion) {
        public ApiSession { if (session == null) throw new IllegalArgumentException("session"); }
    }

    public record PreviewAccess(String url, long expiresAtEpochSecond, String audience,
                                List<String> evidenceRefs) {
        public PreviewAccess {
            bounded(url, "url", 4096); bounded(audience, "audience", 200);
            try {
                java.net.URI uri = java.net.URI.create(url);
                if (!uri.isAbsolute() || !"https".equalsIgnoreCase(uri.getScheme()) || uri.getUserInfo() != null || uri.getFragment() != null)
                    throw new IllegalArgumentException("preview access must be HTTPS");
            } catch (IllegalArgumentException error) { throw new IllegalArgumentException("preview access URL invalid", error); }
            if (expiresAtEpochSecond < 1) throw new IllegalArgumentException("preview access expiry");
            evidenceRefs = List.copyOf(evidenceRefs == null ? List.of() : evidenceRefs);
            if (evidenceRefs.isEmpty()) throw new IllegalArgumentException("preview access evidence required");
        }
    }

    public static long epoch(Instant instant) { return instant.getEpochSecond(); }
    private static void bounded(String value, String field, int maximum) {
        requireText(value, field); if (value.length() > maximum) throw new IllegalArgumentException(field + " too long");
    }
}
