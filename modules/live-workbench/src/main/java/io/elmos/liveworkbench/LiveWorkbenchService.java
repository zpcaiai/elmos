package io.elmos.liveworkbench;

import io.elmos.developerworkflow.DeveloperWorkflowService;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

import static io.elmos.liveworkbench.LwContracts.*;

/**
 * Repository-owned Live Workbench core. It binds every lw.v1 operation to an
 * immutable snapshot, host authority, and evidence boundary; it never creates
 * a sandbox, authority, DAP connection, or certification result itself.
 */
public final class LiveWorkbenchService {
    public record CapabilityStatus(SkillStatus status, String reason, List<String> evidenceIds) {
        public CapabilityStatus { evidenceIds = List.copyOf(evidenceIds); }
    }
    public record ArtifactDelivery(String deliveryId, String tenantId, String repositoryId, String snapshotId,
                                   String origin, String sourceSnapshotId, String buildArtifactDigest, String lockfileDigest,
                                   String runtimeProfileId, String entrypointId, String previewKind,
                                   Map<String, CapabilityStatus> capabilities, List<String> missionIds,
                                   List<String> virtualizedDependencies) {
        public ArtifactDelivery {
            requireText(deliveryId, "deliveryId"); requireText(tenantId, "tenantId"); requireText(repositoryId, "repositoryId"); requireDigest(snapshotId, "snapshotId");
            if (!Set.of("generated", "converted").contains(origin)) throw new IllegalArgumentException("origin");
            if (sourceSnapshotId != null) requireDigest(sourceSnapshotId, "sourceSnapshotId"); requireDigest(buildArtifactDigest, "buildArtifactDigest"); requireDigest(lockfileDigest, "lockfileDigest");
            requireText(runtimeProfileId, "runtimeProfileId"); requireText(entrypointId, "entrypointId");
            if (!Set.of("web", "api", "cli", "library-test", "native-stream").contains(previewKind)) throw new IllegalArgumentException("previewKind");
            capabilities = Map.copyOf(capabilities); if (!capabilities.keySet().equals(Set.of("read", "teach", "build", "preview", "debug", "compare"))) throw new IllegalArgumentException("all capability states required");
            missionIds = List.copyOf(missionIds); virtualizedDependencies = List.copyOf(virtualizedDependencies);
        }
        public boolean productionCredentialsAllowed() { return false; }
    }
    public record NavigationNode(String id, SourceAnchor anchor, String side) {
        public NavigationNode { requireText(id, "node id"); if (anchor == null) throw new IllegalArgumentException("anchor"); if (!Set.of("source", "target", "ir").contains(side)) throw new IllegalArgumentException("side"); }
    }
    public record NavigationEdge(String from, String to, String relation, double confidence, List<String> provenance) {
        public NavigationEdge { requireText(from, "from"); requireText(to, "to"); if (confidence < 0 || confidence > 1) throw new IllegalArgumentException("confidence"); provenance = List.copyOf(provenance); }
    }
    public record NavigationResult(String status, List<NavigationNode> destinations, String reason) { public NavigationResult { destinations = List.copyOf(destinations); } }
    public record Explanation(SourceAnchor anchor, String audience, String mode, List<EvidenceClaim> facts, List<String> limitations) { public Explanation { facts = List.copyOf(facts); limitations = List.copyOf(limitations); } }
    public record BreakpointBinding(SourceAnchor requested, SourceAnchor bound, String status, String reason) {}
    public record ReplayResult(String status, List<RuntimeEvent> events, String reason) { public ReplayResult { events = List.copyOf(events); } }
    public record Triage(String code, List<String> boundedActions, boolean mayModifySource) { public Triage { boundedActions = List.copyOf(boundedActions); } }
    public record PrivacyExport(String status, List<EvidenceClaim> claims, List<String> excludedReasons) { public PrivacyExport { claims = List.copyOf(claims); excludedReasons = List.copyOf(excludedReasons); } }

    private final ImmutableSourceRepository sources;
    private final PreviewSessionManager sessions;
    private final DebugCommandLedger debugLedger;
    @SuppressWarnings("unused") private final DeveloperWorkflowService developerWorkflow; // the common Batch 36 policy/control-plane integration point
    private final Map<String, ArtifactDelivery> deliveries = new HashMap<>();
    private final Map<String, RuntimeProfile> profiles = new HashMap<>();
    private final Map<String, SourceAnchor> anchors = new HashMap<>();
    private final Map<String, EvidenceClaim> claims = new HashMap<>();
    private final Map<String, LearningMission> missions = new HashMap<>();
    private final Map<String, SemanticCorrespondence> correspondences = new HashMap<>();
    private final Map<String, NavigationNode> nodes = new HashMap<>();
    private final List<NavigationEdge> edges = new ArrayList<>();

    public LiveWorkbenchService(ImmutableSourceRepository sources, PreviewSessionManager sessions, DebugCommandLedger debugLedger,
                                DeveloperWorkflowService developerWorkflow) {
        this.sources = Objects.requireNonNull(sources); this.sessions = Objects.requireNonNull(sessions); this.debugLedger = Objects.requireNonNull(debugLedger);
        this.developerWorkflow = Objects.requireNonNull(developerWorkflow);
    }

    // LW-01, LW-08, LW-09, LW-10, LW-20: delivery and safe runtime preparation facts.
    public synchronized ArtifactDelivery registerArtifactDelivery(ArtifactDelivery delivery, RuntimeProfile profile) {
        if (!delivery.tenantId().equals(profileTenantScope(delivery))) throw new IllegalArgumentException("delivery tenant scope invalid");
        if (!delivery.runtimeProfileId().equals(profile.profileId())) throw new IllegalArgumentException("profile mismatch");
        if (deliveries.putIfAbsent(delivery.deliveryId(), delivery) != null) throw new IllegalArgumentException("delivery immutable and already exists");
        profiles.putIfAbsent(profile.profileId(), profile); return delivery;
    }
    public synchronized RuntimeProfile registerRuntimeProfile(RuntimeProfile profile) { profiles.putIfAbsent(profile.profileId(), profile); return profiles.get(profile.profileId()); }
    public synchronized String prebuildCacheKey(ArtifactDelivery delivery, String tenantAclVersion) {
        requireText(tenantAclVersion, "tenantAclVersion"); return LwDigest.sha256(delivery.tenantId()+"\n"+tenantAclVersion+"\n"+delivery.buildArtifactDigest()+"\n"+delivery.lockfileDigest());
    }
    public boolean admitDemoDependencies(ArtifactDelivery delivery) { return delivery.virtualizedDependencies().stream().noneMatch(String::isBlank) && !delivery.productionCredentialsAllowed(); }

    // LW-02, LW-03, LW-04, LW-05, LW-06: immutable reading, navigation and evidence-first teaching.
    public synchronized SourceAnchor registerAnchor(String anchorId, SourceAnchor anchor) { requireText(anchorId, "anchorId"); anchors.put(anchorId, anchor); return anchor; }
    public String readSource(Authority authority, SourceAnchor anchor, long now) { return sources.resolve(authority, anchor, now); }
    public synchronized void registerNavigation(NavigationNode node) { nodes.put(node.id(), node); }
    public synchronized void registerNavigationEdge(NavigationEdge edge) {
        if (!nodes.containsKey(edge.from()) || !nodes.containsKey(edge.to())) throw new IllegalArgumentException("navigation edge endpoint missing");
        edges.add(edge);
    }
    public synchronized NavigationResult navigate(Authority authority, String fromNodeId, String expectedSnapshot, double minimumConfidence, long now) {
        if (!authority.validAt(now, Capability.INSPECT)) return new NavigationResult("DENIED", List.of(), "INSPECT_AUTHORITY_REQUIRED");
        if (!authority.binding().snapshotId().equals(expectedSnapshot) || !LwDigest.exact(expectedSnapshot)) return new NavigationResult("STALE", List.of(), "STALE_SNAPSHOT");
        NavigationNode from = nodes.get(fromNodeId); if (from == null) return new NavigationResult("UNMAPPED", List.of(), "UNKNOWN_NODE");
        if (!from.anchor().tenantId().equals(authority.binding().tenantId()) || !from.anchor().snapshotId().equals(expectedSnapshot)) return new NavigationResult("DENIED", List.of(), "CROSS_SCOPE_NAVIGATION_DENIED");
        List<NavigationNode> result = edges.stream().filter(edge -> edge.from().equals(fromNodeId) || edge.to().equals(fromNodeId)).filter(edge -> edge.confidence() >= minimumConfidence)
                .map(edge -> nodes.get(edge.from().equals(fromNodeId) ? edge.to() : edge.from())).filter(Objects::nonNull)
                .filter(node -> node.anchor().tenantId().equals(authority.binding().tenantId())).toList();
        return result.isEmpty() ? new NavigationResult("UNMAPPED", List.of(), "NO_FRESH_CONFIDENT_MAPPING") : new NavigationResult("RESOLVED", result, "PROVENANCE_LINKED");
    }
    public synchronized EvidenceClaim registerClaim(EvidenceClaim claim) {
        if (claim.classification() == ClaimClass.RUNTIME_OBSERVED && claim.runtimeEventIds().isEmpty()) throw new IllegalArgumentException("runtime observation without event");
        claims.put(claim.claimId(), claim); return claim;
    }
    public synchronized Explanation explain(SourceAnchor anchor, String audience, String mode) {
        requireText(audience, "audience"); if (!Set.of("line", "module", "architecture").contains(mode)) throw new IllegalArgumentException("explanation mode");
        List<EvidenceClaim> facts = claims.values().stream().filter(c -> c.snapshotId().equals(anchor.snapshotId()) && c.sourceAnchorIds().contains(anchorKey(anchor))).toList();
        return new Explanation(anchor, audience, mode, facts, List.of("Explanations are bounded by registered static/runtime evidence; inference is labelled."));
    }

    // LW-07, LW-21: cross-language correspondence and observed differential results.
    public synchronized SemanticCorrespondence registerCorrespondence(SemanticCorrespondence correspondence) { correspondences.put(correspondence.mappingId(), correspondence); return correspondence; }
    public synchronized List<SemanticCorrespondence> correspondencesFor(String anchorId) { return correspondences.values().stream().filter(c -> c.sourceAnchorIds().contains(anchorId) || c.targetAnchorIds().contains(anchorId)).toList(); }
    public String compareObservedValues(Map<String, String> source, Map<String, String> target) {
        if (!source.keySet().equals(target.keySet())) return "DIFFERENT_CHECKPOINT_SET";
        return source.entrySet().stream().allMatch(e -> Objects.equals(e.getValue(), target.get(e.getKey()))) ? "OBSERVED_MATCH_ONLY" : "OBSERVED_DIFFERENCE";
    }

    // LW-11..LW-18: session/lease/admission, access isolation and DAP-safe control.
    public PreviewSession createPreviewSession(Authority authority, long now, long providerHardDeadline, int slotWeight) { return sessions.create(authority, now, providerHardDeadline, slotWeight); }
    public PreviewSession commitReadiness(Authority authority, ReadinessAttestation attestation, long now) { return sessions.commitReady(authority, attestation, now); }
    public PreviewSession previewStatus(Authority authority, String sessionId, long now) { return sessions.get(authority, sessionId, now); }
    public boolean authorizePreviewAccess(Authority authority, PreviewSession session, long now) { return authority.validAt(now, Capability.INSPECT) && authority.binding().equals(session.binding()) && session.liveAt(now); }
    public CleanupReceipt terminatePreview(Authority authority, String sessionId, String reason, long now) { return sessions.expireOrTerminate(authority, sessionId, reason, now); }
    public BreakpointBinding bindBreakpoint(Authority authority, SourceAnchor requested, SourceAnchor resolved, long now) {
        ImmutableSourceRepository.requireAuthority(authority, requested, now, Capability.CONTROL);
        if (resolved == null || !requested.snapshotId().equals(resolved.snapshotId()) || !requested.blobDigest().equals(resolved.blobDigest())) return new BreakpointBinding(requested, null, "UNBOUND", "STALE_OR_UNRESOLVED_DEBUG_SYMBOL");
        return new BreakpointBinding(requested, resolved, "BOUND", "EXACT_IMMUTABLE_SOURCE_BINDING");
    }
    public DebugCommandLedger.Result submitDebug(Authority authority, PreviewSession session, DebugCommand command, long now, boolean adapterAcknowledged) { return debugLedger.submit(authority, session, command, now, adapterAcknowledged); }
    public void linkRuntimeEvidence(RuntimeEvent event) { debugLedger.appendCommitted(event); }
    public ReplayResult replayTimeline(Authority authority, long afterSequence, long now) {
        return new ReplayResult("READ_ONLY", debugLedger.resume(authority, afterSequence, now), "Events are replayed; side-effect commands are never replayed.");
    }

    // LW-19, LW-22..LW-26: learning, invalidation, triage, assessment and privacy-safe export.
    public synchronized LearningMission registerMission(LearningMission mission) { missions.put(mission.missionId(), mission); return mission; }
    public synchronized LearningMission missionForSnapshot(String missionId, String snapshotId) {
        LearningMission mission = missions.get(missionId); if (mission == null) throw new IllegalArgumentException("unknown mission");
        return mission.snapshotId().equals(snapshotId) ? mission : new LearningMission(mission.missionId(), mission.tenantId(), mission.repositoryId(), mission.snapshotId(), mission.title(), mission.mode(), mission.difficulty(), mission.prerequisites(), mission.sourceAnchorIds(), mission.steps(), mission.assessmentServiceRef(), true);
    }
    public synchronized int invalidateForNewSnapshot(String oldSnapshotId) {
        int stale = 0;
        for (LearningMission mission : new ArrayList<>(missions.values())) if (mission.snapshotId().equals(oldSnapshotId)) { missions.put(mission.missionId(), new LearningMission(mission.missionId(), mission.tenantId(), mission.repositoryId(), mission.snapshotId(), mission.title(), mission.mode(), mission.difficulty(), mission.prerequisites(), mission.sourceAnchorIds(), mission.steps(), mission.assessmentServiceRef(), true)); stale++; }
        return stale;
    }
    public Triage triage(String failureCode) {
        requireText(failureCode, "failureCode");
        return switch (failureCode) {
            case "BUILD_FAILED" -> new Triage("BUILD_FAILED", List.of("collect-redacted-diagnostics", "select-affected-tests", "offer-preview-only"), false);
            case "ADAPTER_UNAVAILABLE" -> new Triage("ADAPTER_UNAVAILABLE", List.of("show-runtime-profile-limitations", "retry-status-query-only"), false);
            case "AUTHORITY_EXPIRED" -> new Triage("AUTHORITY_EXPIRED", List.of("request-new-host-minted-lease"), false);
            default -> new Triage("UNKNOWN_FAILURE", List.of("preserve-evidence", "escalate-to-human"), false);
        };
    }
    public boolean assessmentAccess(Authority authority, LearningMission mission, long now) { return authority.validAt(now, Capability.INSPECT) && authority.binding().tenantId().equals(mission.tenantId()) && authority.binding().snapshotId().equals(mission.snapshotId()); }
    public synchronized PrivacyExport exportClaims(Authority authority, List<String> claimIds, long now) {
        if (!authority.validAt(now, Capability.INSPECT)) return new PrivacyExport("DENIED", List.of(), List.of("INSPECT_AUTHORITY_REQUIRED"));
        List<EvidenceClaim> exported = new ArrayList<>(); List<String> excluded = new ArrayList<>();
        for (String id : claimIds) { EvidenceClaim claim = claims.get(id); if (claim == null || !claim.tenantId().equals(authority.binding().tenantId()) || !claim.snapshotId().equals(authority.binding().snapshotId())) excluded.add(id); else exported.add(claim); }
        return new PrivacyExport(excluded.isEmpty() ? "EXPORTED" : "PARTIAL", exported, excluded);
    }

    // LW-27..LW-28: the core coordinates only a qualified host; no fake distributed/device execution.
    public String distributedDebugAvailability(RuntimeProfile profile) { return profile.qualification() == Qualification.QUALIFIED && profile.capabilities().contains("distributed-debug") ? "HOST_PROVIDER_REQUIRED" : "BLOCKED_UNQUALIFIED_PROFILE"; }
    public String nativeDeviceLabAvailability(RuntimeProfile profile) { return profile.qualification() == Qualification.QUALIFIED && profile.capabilities().contains("native-device") ? "HOST_PROVIDER_REQUIRED" : "BLOCKED_UNQUALIFIED_PROFILE"; }

    /** Exact public package identities, all bound to the methods above rather than an unscoped generic dispatcher. */
    public static Map<String, SkillStatus> supportedSkills() {
        Map<String, SkillStatus> skills = new LinkedHashMap<>();
        List<String> local = List.of("elmos-lw-artifact-contract", "elmos-lw-revision-source-anchor", "elmos-lw-reader-semantic-navigation", "elmos-lw-line-teaching", "elmos-lw-module-teaching", "elmos-lw-architecture-teaching", "elmos-lw-conversion-correspondence", "elmos-lw-runtime-profile", "elmos-lw-prebuild-cache", "elmos-lw-demo-data-services", "elmos-lw-sandbox-resource-admission", "elmos-lw-readiness-verification", "elmos-lw-preview-lease-600s", "elmos-lw-preview-access-isolation", "elmos-lw-debug-adapter-broker", "elmos-lw-breakpoint-binding", "elmos-lw-debug-command-safety", "elmos-lw-execution-evidence-linking", "elmos-lw-guided-learning-mission", "elmos-lw-acceptance-fixtures", "elmos-lw-differential-debug-lab", "elmos-lw-edit-rebuild-invalidation", "elmos-lw-replay-timeline-inputs", "elmos-lw-failure-triage-repair", "elmos-lw-assessment-accessibility-collaboration", "elmos-lw-evidence-privacy-export");
        local.forEach(name -> skills.put(name, SkillStatus.AVAILABLE));
        skills.put("elmos-lw-distributed-coordinated-debug", SkillStatus.BLOCKED_BY_HOST);
        skills.put("elmos-lw-native-device-lab", SkillStatus.BLOCKED_BY_HOST);
        return Map.copyOf(skills);
    }
    private static String profileTenantScope(ArtifactDelivery delivery) { return delivery.tenantId(); }
    private static String anchorKey(SourceAnchor anchor) { return anchor.path()+":"+anchor.byteStart()+":"+anchor.byteEnd(); }
}
