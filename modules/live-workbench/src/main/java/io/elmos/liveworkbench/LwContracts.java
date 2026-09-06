package io.elmos.liveworkbench;

import java.util.List;
import java.util.Map;
import java.util.Set;

/** Typed, repository-owned lw.v1 contracts. Browser clients never mint Authority. */
public final class LwContracts {
    private LwContracts() {}
    public static final String VERSION = "lw.v1";
    public static final long PREVIEW_SECONDS = 600;
    public static final long CLEANUP_SECONDS = 30;
    public static final int MAX_ACCOUNT_SLOTS = 3;

    public enum Capability { INSPECT, CONTROL, MUTATE, HOST_EXEC }
    public enum SessionState { PREPARING, READY, EXPIRED, TERMINATED, CLEANUP_PENDING, CLEANED, QUARANTINED, FAILED }
    public enum RuntimeStatus { PENDING, RUNNING, STOPPED, DEGRADED, UNKNOWN }
    public enum Qualification { CANDIDATE, QUALIFIED, UNSUPPORTED, NOT_RUN }
    public enum CommandState { PENDING, COMMITTED, UNKNOWN, DENIED }
    public enum ClaimClass { VERIFIED_STATIC, RUNTIME_OBSERVED, INFERRED, UNKNOWN, RECOMMENDED }
    public enum SkillStatus { AVAILABLE, BLOCKED_BY_HOST, NOT_RUN_EXTERNAL }

    public record Binding(String tenantId, String repositoryId, String snapshotId, String sessionId, int generation) {
        public Binding {
            requireText(tenantId, "tenantId"); requireText(repositoryId, "repositoryId");
            requireDigest(snapshotId, "snapshotId"); requireText(sessionId, "sessionId");
            if (generation < 1) throw new IllegalArgumentException("generation must be positive");
        }
    }
    public record Authority(String handle, String accountId, String environmentId, String capabilityLeaseId,
                            long expiresAt, Binding binding, Set<Capability> capabilities) {
        public Authority {
            requireText(handle, "handle"); requireText(accountId, "accountId"); requireText(environmentId, "environmentId");
            requireText(capabilityLeaseId, "capabilityLeaseId"); if (expiresAt < 0) throw new IllegalArgumentException("expiresAt");
            if (binding == null) throw new IllegalArgumentException("binding required"); capabilities = Set.copyOf(capabilities);
        }
        public boolean validAt(long now, Capability capability) { return now < expiresAt && capabilities.contains(capability); }
    }
    public record SourceAnchor(String tenantId, String repositoryId, String snapshotId, String path, String blobDigest,
                               int byteStart, int byteEnd, String coordinateSystem, String symbolId) {
        public SourceAnchor {
            requireText(tenantId, "tenantId"); requireText(repositoryId, "repositoryId"); requireDigest(snapshotId, "snapshotId");
            safePath(path); requireDigest(blobDigest, "blobDigest");
            if (byteStart < 0 || byteEnd < byteStart) throw new IllegalArgumentException("invalid byte range");
            if (!"utf8-byte-half-open".equals(coordinateSystem)) throw new IllegalArgumentException("unsupported coordinate system");
        }
    }
    public record RuntimeProfile(String profileId, String language, String framework, String runtime, String os, String arch,
                                 String adapter, String adapterVersion, String runtimeDigest, String previewKind,
                                 Qualification qualification, Set<String> capabilities, List<String> evidenceIds,
                                 List<String> limitations, boolean licenseReviewRequired) {
        public RuntimeProfile {
            requireText(profileId, "profileId"); requireText(language, "language"); requireText(runtime, "runtime");
            requireText(os, "os"); requireText(arch, "arch"); requireText(adapter, "adapter"); requireText(adapterVersion, "adapterVersion");
            requireDigest(runtimeDigest, "runtimeDigest"); requireText(previewKind, "previewKind");
            if (qualification == null) throw new IllegalArgumentException("qualification"); capabilities = Set.copyOf(capabilities);
            evidenceIds = List.copyOf(evidenceIds); limitations = List.copyOf(limitations);
        }
    }
    public record PreviewSession(Binding binding, SessionState state, RuntimeStatus runtimeStatus, long createdAt,
                                 Long firstReadyAt, Long expiresAt, long prepareBudgetSeconds, long cleanupBudgetSeconds,
                                 long providerHardDeadline, int slotWeight, String readinessId, boolean clientCanExtend) {
        public PreviewSession {
            if (binding == null) throw new IllegalArgumentException("binding"); if (state == null || runtimeStatus == null) throw new IllegalArgumentException("state");
            if (createdAt < 0 || prepareBudgetSeconds != PREVIEW_SECONDS || cleanupBudgetSeconds != CLEANUP_SECONDS || slotWeight < 1)
                throw new IllegalArgumentException("invalid fixed lifecycle budget");
            if (clientCanExtend) throw new IllegalArgumentException("client must never extend preview");
            if (state == SessionState.READY && (firstReadyAt == null || expiresAt == null || readinessId == null))
                throw new IllegalArgumentException("ready requires attestation and fixed deadline");
            if (firstReadyAt != null && expiresAt != firstReadyAt + PREVIEW_SECONDS) throw new IllegalArgumentException("preview window must be exactly 600 seconds");
        }
        public boolean liveAt(long now) { return state == SessionState.READY && expiresAt != null && now < expiresAt; }
    }
    public record ReadinessAttestation(String id, Binding binding, String artifactDigest, String verifierId,
                                       String hostSignatureRef, long verifiedAt, Map<String, Boolean> checks,
                                       List<String> evidenceIds, boolean committed) {
        public ReadinessAttestation {
            requireText(id, "id"); if (binding == null) throw new IllegalArgumentException("binding"); requireDigest(artifactDigest, "artifactDigest");
            requireText(verifierId, "verifierId"); requireText(hostSignatureRef, "hostSignatureRef"); checks = Map.copyOf(checks); evidenceIds = List.copyOf(evidenceIds);
            if (!committed || !checks.values().stream().allMatch(Boolean::booleanValue)) throw new IllegalArgumentException("readiness must be committed and fully verified");
        }
    }
    public record DebugCommand(Binding binding, String commandId, String idempotencyKey, int stopEpoch,
                               String controlLeaseId, String command, String argumentsDigest, Capability requiredCapability,
                               String authorizationRef, long deadline) {
        public DebugCommand {
            if (binding == null) throw new IllegalArgumentException("binding"); requireText(commandId, "commandId"); requireText(idempotencyKey, "idempotencyKey");
            if (stopEpoch < 0) throw new IllegalArgumentException("stopEpoch"); requireText(controlLeaseId, "controlLeaseId");
            if (!Set.of("continue", "pause", "next", "stepIn", "stepOut", "terminate", "stackTrace", "variables").contains(command))
                throw new IllegalArgumentException("command is not allowlisted");
            requireDigest(argumentsDigest, "argumentsDigest"); if (requiredCapability != Capability.CONTROL && requiredCapability != Capability.INSPECT)
                throw new IllegalArgumentException("debug capability invalid"); requireText(authorizationRef, "authorizationRef");
        }
    }
    public record RuntimeEvent(String eventId, Binding binding, int stopEpoch, long sequence, String kind, long serverTime,
                               List<String> sourceAnchorIds, String payloadDigest, boolean committed, String redactionStatus) {
        public RuntimeEvent {
            requireText(eventId, "eventId"); if (binding == null || stopEpoch < 0 || sequence < 1) throw new IllegalArgumentException("event binding");
            requireText(kind, "kind"); sourceAnchorIds = List.copyOf(sourceAnchorIds); requireDigest(payloadDigest, "payloadDigest");
            if (!committed) throw new IllegalArgumentException("only committed event can enter ledger");
            if (!Set.of("none-needed", "redacted", "omitted").contains(redactionStatus)) throw new IllegalArgumentException("redaction status");
        }
    }
    public record EvidenceClaim(String claimId, String tenantId, String repositoryId, String snapshotId, String text,
                                ClaimClass classification, List<String> sourceAnchorIds, List<String> runtimeEventIds,
                                List<String> assumptions, List<String> limitations, String generatorVersion) {
        public EvidenceClaim {
            requireText(claimId, "claimId"); requireText(tenantId, "tenantId"); requireText(repositoryId, "repositoryId"); requireDigest(snapshotId, "snapshotId");
            requireText(text, "text"); if (classification == null) throw new IllegalArgumentException("classification");
            sourceAnchorIds = List.copyOf(sourceAnchorIds); runtimeEventIds = List.copyOf(runtimeEventIds);
            assumptions = List.copyOf(assumptions); limitations = List.copyOf(limitations); requireText(generatorVersion, "generatorVersion");
            if (classification == ClaimClass.RUNTIME_OBSERVED && runtimeEventIds.isEmpty()) throw new IllegalArgumentException("runtime claim requires committed event");
            if ((classification == ClaimClass.VERIFIED_STATIC || classification == ClaimClass.RUNTIME_OBSERVED) && sourceAnchorIds.isEmpty()) throw new IllegalArgumentException("factual claim requires source anchor");
        }
    }
    public record SemanticCorrespondence(String mappingId, String tenantId, String sourceSnapshotId, String targetSnapshotId,
                                         String relation, List<String> sourceAnchorIds, List<String> irSymbolIds,
                                         List<String> targetAnchorIds, String ruleId, String confidence,
                                         List<String> checkpointIds, List<String> assumptions, List<String> evidenceIds) {
        public SemanticCorrespondence {
            requireText(mappingId, "mappingId"); requireText(tenantId, "tenantId"); requireDigest(sourceSnapshotId, "sourceSnapshotId"); requireDigest(targetSnapshotId, "targetSnapshotId");
            if (!Set.of("one-to-one", "one-to-many", "many-to-one", "many-to-many", "deleted", "synthesized", "unmapped").contains(relation)) throw new IllegalArgumentException("relation");
            sourceAnchorIds = List.copyOf(sourceAnchorIds); irSymbolIds = List.copyOf(irSymbolIds); targetAnchorIds = List.copyOf(targetAnchorIds);
            if (!Set.of("rule-derived", "observed-scenario", "inferred", "unknown").contains(confidence)) throw new IllegalArgumentException("confidence");
            checkpointIds = List.copyOf(checkpointIds); assumptions = List.copyOf(assumptions); evidenceIds = List.copyOf(evidenceIds);
        }
        public boolean universalEquivalenceProven() { return false; }
    }
    public record LearningMission(String missionId, String tenantId, String repositoryId, String snapshotId, String title,
                                  String mode, String difficulty, List<String> prerequisites, List<String> sourceAnchorIds,
                                  List<MissionStep> steps, String assessmentServiceRef, boolean stale) {
        public LearningMission {
            requireText(missionId, "missionId"); requireText(tenantId, "tenantId"); requireText(repositoryId, "repositoryId"); requireDigest(snapshotId, "snapshotId"); requireText(title, "title");
            if (!Set.of("Observe", "Guided", "Challenge", "Free", "Compare").contains(mode)) throw new IllegalArgumentException("mode");
            if (!Set.of("beginner", "engineer", "cross-language").contains(difficulty)) throw new IllegalArgumentException("difficulty");
            prerequisites = List.copyOf(prerequisites); sourceAnchorIds = List.copyOf(sourceAnchorIds); steps = List.copyOf(steps);
            if (sourceAnchorIds.isEmpty() || steps.isEmpty()) throw new IllegalArgumentException("mission evidence required"); requireText(assessmentServiceRef, "assessmentServiceRef");
        }
        /** Private grader reference only: answers are intentionally absent from the public contract. */
        public boolean answerInPublicPayload() { return false; }
    }
    public record MissionStep(String stepId, String instruction, String action, String completionPredicateId, List<String> hintIds) {
        public MissionStep { requireText(stepId, "stepId"); requireText(instruction, "instruction");
            if (!Set.of("read", "predict", "run", "breakpoint", "inspect", "compare", "edit", "test").contains(action)) throw new IllegalArgumentException("mission action");
            requireText(completionPredicateId, "completionPredicateId"); hintIds = List.copyOf(hintIds); }
    }
    public record CleanupReceipt(Binding binding, long deadline, long observedAt, Map<String, Boolean> checks,
                                 SessionState status, String verifierId, List<String> evidenceIds) {
        public CleanupReceipt { if (binding == null) throw new IllegalArgumentException("binding"); if (observedAt < deadline) throw new IllegalArgumentException("cleanup before deadline");
            checks = Map.copyOf(checks); if (status != SessionState.CLEANED && status != SessionState.QUARANTINED) throw new IllegalArgumentException("cleanup status"); requireText(verifierId, "verifierId"); evidenceIds = List.copyOf(evidenceIds); }
    }
    static void requireText(String value, String field) { if (value == null || value.isBlank()) throw new IllegalArgumentException(field + " required"); }
    static void requireDigest(String value, String field) { if (!LwDigest.exact(value)) throw new IllegalArgumentException(field + " must be sha256"); }
    static void safePath(String path) { requireText(path, "path"); if (path.startsWith("/") || path.contains("\\") || path.contains("\u0000") || List.of(path.split("/")).contains("..")) throw new IllegalArgumentException("path outside snapshot"); }
}
