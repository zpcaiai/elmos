package io.elmos.proofloop;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.regex.Pattern;

/** Typed contracts for the Batch 105-108 modernization proof loop. */
public final class ProofLoopModels {
    private ProofLoopModels() {}

    private static final Pattern ID = Pattern.compile("[A-Za-z0-9][A-Za-z0-9._:@/-]{0,199}");
    private static final Pattern ARTIFACT_NAME = Pattern.compile("[A-Za-z0-9][A-Za-z0-9._*+@/-]{0,239}");
    private static final Pattern MEDIA_TYPE = Pattern.compile("[a-z0-9][a-z0-9.+-]{0,63}/[a-z0-9][a-z0-9.+-]{0,63}");
    private static final Pattern SHA256 = Pattern.compile("(?:sha256:)?[a-f0-9]{64}");
    private static final Pattern COMMIT = Pattern.compile("[a-f0-9]{40,64}");
    private static final Pattern SKILL = Pattern.compile("B10[5-8]-S(?:0[1-9]|1[0-6])");

    public enum EvidenceState { VERIFIED, FAILED, NOT_RUN, BLOCKED, UNKNOWN, INCONCLUSIVE, NOT_APPLICABLE }
    public enum RunState { PASSED, PARTIAL, BLOCKED, FAILED }
    public enum ExecutionClass { CONTROL_PLANE, ISOLATED_RUNNER, INDEPENDENT_GATE }
    public enum CertificateLevel {
        NONE, CODE_MODIFIED, BUILD_VERIFIED, TEST_VERIFIED, API_VERIFIED,
        RUNTIME_VERIFIED, DEMO_READY, CUSTOMER_REVIEW_READY, PRODUCTION_CANDIDATE
    }

    public record Subject(
            String organizationId,
            String projectId,
            String repositoryId,
            String baselineCommit,
            String candidateCommit,
            String imageDigest,
            String policyDigest
    ) {
        public Subject {
            identifier(organizationId, "organizationId");
            identifier(projectId, "projectId");
            identifier(repositoryId, "repositoryId");
            optionalCommit(baselineCommit, "baselineCommit");
            optionalCommit(candidateCommit, "candidateCommit");
            optionalDigest(imageDigest, "imageDigest");
            digest(policyDigest, "policyDigest");
        }
    }

    public record EvidenceAssertion(
            EvidenceState state,
            String subjectDigest,
            String producerId,
            String verifierId,
            Instant observedAt,
            boolean signatureVerified,
            boolean bytesRecomputed,
            List<String> artifactRefs
    ) {
        public EvidenceAssertion {
            required(state, "state");
            digest(subjectDigest, "subjectDigest");
            identifier(producerId, "producerId");
            identifier(verifierId, "verifierId");
            required(observedAt, "observedAt");
            artifactRefs = copy(artifactRefs);
        }

        public boolean independentlyVerified(Instant now, long maximumAgeSeconds) {
            return state == EvidenceState.VERIFIED
                    && !producerId.equals(verifierId)
                    && signatureVerified
                    && bytesRecomputed
                    && !artifactRefs.isEmpty()
                    && !observedAt.isAfter(now)
                    && !observedAt.isBefore(now.minusSeconds(maximumAgeSeconds));
        }
    }

    public record ExecutionRequest(
            String runId,
            String requestId,
            String skillId,
            String actorId,
            Subject subject,
            Instant requestedAt,
            Map<String, Object> inputs,
            Map<String, EvidenceAssertion> evidence
    ) {
        public ExecutionRequest {
            identifier(runId, "runId");
            identifier(requestId, "requestId");
            if (skillId == null || !SKILL.matcher(skillId).matches()) {
                throw new IllegalArgumentException("skillId is not a Batch 105-108 Skill");
            }
            identifier(actorId, "actorId");
            required(subject, "subject");
            required(requestedAt, "requestedAt");
            inputs = immutableMap(inputs);
            evidence = evidence == null ? Map.of() : Map.copyOf(evidence);
        }
    }

    public record Artifact(
            String name,
            String mediaType,
            String sha256,
            long byteCount,
            String producer,
            String subjectDigest,
            Instant createdAt,
            Map<String, Object> content
    ) {
        public Artifact {
            if (name == null || name.startsWith("/") || name.contains("..") || !ARTIFACT_NAME.matcher(name).matches()) {
                throw new IllegalArgumentException("name must be a safe contract-relative artifact path");
            }
            if (mediaType == null || !MEDIA_TYPE.matcher(mediaType).matches()) {
                throw new IllegalArgumentException("mediaType is invalid");
            }
            digest(sha256, "sha256");
            if (byteCount <= 0) throw new IllegalArgumentException("byteCount must be positive");
            identifier(producer, "producer");
            digest(subjectDigest, "subjectDigest");
            required(createdAt, "createdAt");
            content = immutableMap(content);
        }
    }

    public record SkillResult(
            String runId,
            String requestId,
            String skillId,
            String skillName,
            int batch,
            RunState state,
            List<String> claims,
            List<String> findings,
            List<Artifact> artifacts,
            String requestDigest,
            String resultDigest,
            Instant startedAt,
            Instant finishedAt,
            boolean externalOperationExecuted,
            boolean certified,
            CertificateLevel certificateLevel
    ) {
        public SkillResult {
            identifier(runId, "runId");
            identifier(requestId, "requestId");
            if (skillId == null || !SKILL.matcher(skillId).matches()) throw new IllegalArgumentException("invalid skillId");
            identifier(skillName, "skillName");
            if (batch < 105 || batch > 108) throw new IllegalArgumentException("invalid batch");
            required(state, "state");
            claims = copy(claims);
            findings = copy(findings);
            artifacts = copy(artifacts);
            digest(requestDigest, "requestDigest");
            digest(resultDigest, "resultDigest");
            required(startedAt, "startedAt");
            required(finishedAt, "finishedAt");
            required(certificateLevel, "certificateLevel");
            if (externalOperationExecuted || certified) {
                throw new IllegalArgumentException("the proof-loop kernel cannot claim external execution or certification");
            }
            if (state == RunState.PASSED && artifacts.isEmpty()) {
                throw new IllegalArgumentException("a passed Skill requires immutable artifacts");
            }
            if (state == RunState.PASSED && !findings.isEmpty()) {
                throw new IllegalArgumentException("a passed Skill cannot retain blocking findings");
            }
        }
    }

    public record PlanResult(
            String planId,
            String targetSkillId,
            List<SkillResult> steps,
            RunState state,
            List<String> blockers,
            CertificateLevel highestLevel,
            boolean productionApproved,
            boolean certified
    ) {
        public PlanResult {
            identifier(planId, "planId");
            if (targetSkillId == null || !SKILL.matcher(targetSkillId).matches()) throw new IllegalArgumentException("invalid targetSkillId");
            steps = copy(steps);
            required(state, "state");
            blockers = copy(blockers);
            required(highestLevel, "highestLevel");
            if (productionApproved || certified) {
                throw new IllegalArgumentException("repository execution cannot approve production or certify");
            }
        }
    }

    static void identifier(String value, String field) {
        if (value == null || !ID.matcher(value).matches()) throw new IllegalArgumentException(field + " is invalid");
    }
    static void digest(String value, String field) {
        if (value == null || !SHA256.matcher(value).matches()) throw new IllegalArgumentException(field + " must be SHA-256");
    }
    static void optionalDigest(String value, String field) { if (value != null && !value.isBlank()) digest(value, field); }
    static void optionalCommit(String value, String field) {
        if (value != null && !value.isBlank() && !COMMIT.matcher(value).matches()) throw new IllegalArgumentException(field + " must be an immutable commit");
    }
    public static <T> T required(T value, String field) { return Objects.requireNonNull(value, field + " is required"); }
    static <T> List<T> copy(List<T> value) { return value == null ? List.of() : List.copyOf(value); }
    static Map<String, Object> immutableMap(Map<String, Object> value) { return value == null ? Map.of() : Map.copyOf(value); }
}
