package io.elmos.delivery;

import io.elmos.validation.ValidationModels.Status;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class DeliveryModels {
    private DeliveryModels() {}

    public enum SnapshotStatus { INCOMPLETE, READY_WITH_WARNINGS, READY, BLOCKED, STALE }
    public enum RiskSeverity { LOW, MEDIUM, HIGH, CRITICAL }
    public enum RiskStatus { OPEN, MITIGATED, ACCEPTED, EXPIRED, CLOSED }
    public enum ScmProvider { GITHUB, GITLAB }
    public enum GitLabTier { FREE, PREMIUM, ULTIMATE }
    public enum CheckTransport { GITHUB_CHECK_RUN, GITLAB_EXTERNAL_STATUS, GITLAB_COMMIT_STATUS }
    public enum CheckConclusion { QUEUED, IN_PROGRESS, SUCCESS, NEUTRAL, FAILURE, ACTION_REQUIRED, STALE }
    public enum RollbackActionType { REVERT_CODE, ROLLBACK_DATABASE, RESTORE_DATABASE, ROLL_FORWARD,
        INVALIDATE_CACHE, DUAL_READ_CACHE, REPLAY_MESSAGES, COMPENSATE_MESSAGES,
        ROLLBACK_DEPLOYMENT, SHIFT_TRAFFIC }
    public enum DrillStatus { NOT_RUN, PASSED, FAILED, WAIVED }
    public enum AcceptanceStatus { NOT_READY, READY_FOR_ACCEPTANCE, CONDITIONALLY_ACCEPTED, ACCEPTED, REJECTED }
    public enum DeliveryLifecycle { DELIVERED, ACCEPTED, MERGED, RELEASED, CLOSED, REOPENED }

    public record EvidenceFact(String factId, String domain, String status, String summary,
                               List<String> evidenceRefs, Map<String,Object> metrics) {
        public EvidenceFact {
            require(factId, "factId"); require(domain, "domain"); require(status, "status"); require(summary, "summary");
            evidenceRefs = List.copyOf(evidenceRefs); metrics = Map.copyOf(metrics);
        }
    }

    public record RiskItem(String riskId, String fingerprint, RiskSeverity severity, RiskStatus status,
                           String title, String owner, Instant expiresAt, String acceptanceRef,
                           List<String> evidenceRefs) {
        public RiskItem {
            require(riskId, "riskId"); require(fingerprint, "fingerprint"); require(title, "title");
            require(owner, "owner"); evidenceRefs = List.copyOf(evidenceRefs);
            if (status == RiskStatus.ACCEPTED && (acceptanceRef == null || acceptanceRef.isBlank() || expiresAt == null))
                throw new IllegalArgumentException("accepted risk requires a time-bounded acceptance reference");
        }
        public boolean blocks(Instant at) {
            boolean expiredAcceptance = status == RiskStatus.ACCEPTED && expiresAt != null && !at.isBefore(expiresAt);
            return severity == RiskSeverity.CRITICAL && (status == RiskStatus.OPEN || status == RiskStatus.EXPIRED || expiredAcceptance);
        }
    }

    public record DeliverySnapshot(String schemaVersion, String snapshotId, String migrationId,
                                   String sourceSnapshotId, String sourceCommit, String deliveryHeadSha,
                                   String validationDecisionId, Status validationStatus,
                                   List<EvidenceFact> facts, List<RiskItem> risks,
                                   String rollbackPlanId, String evidencePackId,
                                   SnapshotStatus status, List<String> blockingReasons,
                                   String contentHash, Instant createdAt) {
        public DeliverySnapshot {
            schema(schemaVersion); require(snapshotId, "snapshotId"); require(migrationId, "migrationId");
            require(sourceSnapshotId, "sourceSnapshotId"); require(sourceCommit, "sourceCommit");
            require(deliveryHeadSha, "deliveryHeadSha"); facts = List.copyOf(facts); risks = List.copyOf(risks);
            blockingReasons = List.copyOf(blockingReasons); digest(contentHash, "contentHash");
        }
    }

    public record ReportBundle(String authoritativeJson, String markdown, String html, String factsHash) {}

    public record ScmDeliveryPlan(String planId, ScmProvider provider, String repository,
                                  String branchName, String baseBranch, String headSha,
                                  String title, String body, boolean draft, boolean forcePush,
                                  boolean autoMerge, List<String> reviewerSuggestions,
                                  String idempotencyKey) {
        public ScmDeliveryPlan { reviewerSuggestions = List.copyOf(reviewerSuggestions); }
    }

    public record Annotation(String path, int startLine, int endLine, String level,
                             String title, String message, String evidenceRef) {}
    public record CheckPublication(String checkId, ScmProvider provider, CheckTransport transport,
                                   String name, String boundHeadSha, CheckConclusion conclusion,
                                   List<List<Annotation>> annotationBatches, String summary,
                                   boolean stale) {
        public CheckPublication {
            annotationBatches = annotationBatches.stream().map(List::copyOf).toList();
        }
    }

    public record EvidenceEntry(String path, byte[] content, String mediaType, boolean sensitive) {
        public EvidenceEntry {
            require(path, "path"); require(mediaType, "mediaType"); content = content.clone();
        }
        @Override public byte[] content() { return content.clone(); }
    }
    public record EvidenceManifestEntry(String path, String sha256, long size, String mediaType) {}
    public record EvidencePack(String packId, byte[] archive, byte[] manifest, byte[] signature,
                               byte[] publicKey, String archiveSha256, List<EvidenceManifestEntry> entries) {
        public EvidencePack {
            archive = archive.clone(); manifest = manifest.clone(); signature = signature.clone(); publicKey = publicKey.clone();
            entries = List.copyOf(entries);
        }
        @Override public byte[] archive() { return archive.clone(); }
        @Override public byte[] manifest() { return manifest.clone(); }
        @Override public byte[] signature() { return signature.clone(); }
        @Override public byte[] publicKey() { return publicKey.clone(); }
    }

    public record Change(String domain, String description, boolean reversible, boolean destructive,
                         boolean backwardCompatible, String artifactRef) {}
    public record RollbackStep(int order, RollbackActionType action, String commandTemplate,
                               String precondition, String verification, boolean requiresApproval) {}
    public record RollbackPlan(String schemaVersion, String planId, String migrationId,
                               List<String> triggers, List<RollbackStep> steps,
                               Integer rtoMinutes, Integer rpoMinutes, DrillStatus drillStatus,
                               List<String> limitations, boolean executable, List<String> blockingReasons) {
        public RollbackPlan {
            schema(schemaVersion); triggers = List.copyOf(triggers); steps = List.copyOf(steps);
            limitations = List.copyOf(limitations); blockingReasons = List.copyOf(blockingReasons);
        }
    }

    public record AcceptanceCriterion(String criterionId, String description, boolean required,
                                      boolean satisfied, String evidenceRef) {}
    public record AcceptancePackage(String acceptanceId, String migrationId, String deliveredHeadSha,
                                    String currentHeadSha, AcceptanceStatus acceptanceStatus,
                                    DeliveryLifecycle lifecycle, List<AcceptanceCriterion> criteria,
                                    List<String> conditions, String acceptedBy, Instant acceptedAt,
                                    List<String> blockingReasons) {
        public AcceptancePackage {
            criteria = List.copyOf(criteria); conditions = List.copyOf(conditions); blockingReasons = List.copyOf(blockingReasons);
        }
    }

    static void require(String value, String field) { if (value == null || value.isBlank()) throw new IllegalArgumentException(field + " is required"); }
    static void schema(String value) { if (!"1.0".equals(value)) throw new IllegalArgumentException("unsupported schema version"); }
    static void digest(String value, String field) { if (value == null || !value.matches("[0-9a-f]{64}")) throw new IllegalArgumentException(field + " must be a raw sha256 digest"); }
}
