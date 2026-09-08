package io.elmos.liveworkbench;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

import static io.elmos.liveworkbench.LiveWorkbenchService.ArtifactDelivery;
import static io.elmos.liveworkbench.LwContracts.*;
import static io.elmos.liveworkbench.ProductionContracts.*;

@RestController
@RequestMapping("/api/v1/live-workbench")
public final class LiveWorkbenchCatalogController {
    public record AnchorEnvelope(String anchorId, SourceAnchor anchor) {}
    public record InvalidationEnvelope(String snapshotId) {}

    private final ProductionLiveWorkbenchKnowledgeService knowledge;
    private final PrincipalScopeResolver scopes;

    public LiveWorkbenchCatalogController(ProductionLiveWorkbenchKnowledgeService knowledge, PrincipalScopeResolver scopes) {
        this.knowledge = knowledge; this.scopes = scopes;
    }

    @PostMapping("/catalog/runtime-profiles") RuntimeProfile registerProfile(Authentication auth, @RequestBody RuntimeProfile value) {
        return knowledge.registerProfile(scopes.resolve(auth), value);
    }
    @PostMapping("/catalog/deliveries") ArtifactDelivery registerDelivery(Authentication auth, @RequestBody ArtifactDelivery value) {
        return knowledge.registerDelivery(scopes.resolve(auth), value);
    }
    @GetMapping("/deliveries/{id}") ArtifactDelivery delivery(Authentication auth, @PathVariable String id) {
        return knowledge.delivery(scopes.resolve(auth), id);
    }
    @PostMapping("/catalog/anchors") SourceAnchor registerAnchor(Authentication auth, @RequestBody AnchorEnvelope value) {
        return knowledge.registerAnchor(scopes.resolve(auth), value.anchorId(), value.anchor());
    }
    @GetMapping("/anchors/{id}/source") SourceContent source(Authentication auth, @PathVariable String id) {
        return knowledge.source(scopes.resolve(auth), id);
    }
    @PostMapping("/catalog/claims") EvidenceClaim registerClaim(Authentication auth, @RequestBody EvidenceClaim value) {
        return knowledge.registerClaim(scopes.resolve(auth), value);
    }
    @PostMapping("/explanations") ExplanationView explain(Authentication auth, @RequestBody ExplanationRequest value) {
        return knowledge.explain(scopes.resolve(auth), value);
    }
    @PostMapping("/catalog/missions") LearningMission registerMission(Authentication auth, @RequestBody LearningMission value) {
        return knowledge.registerMission(scopes.resolve(auth), value);
    }
    @GetMapping("/missions/{id}") LearningMission mission(Authentication auth, @PathVariable String id) {
        return knowledge.mission(scopes.resolve(auth), id);
    }
    @PostMapping("/missions/{id}/attempts") MissionAttemptReceipt attempt(Authentication auth, @PathVariable String id,
            @RequestHeader("Idempotency-Key") String idempotencyKey, @RequestBody MissionAttemptRequest value) {
        return knowledge.attempt(scopes.resolve(auth), id, value, idempotencyKey);
    }
    @PostMapping("/catalog/correspondences") SemanticCorrespondence registerCorrespondence(Authentication auth,
            @RequestBody SemanticCorrespondence value) {
        return knowledge.registerCorrespondence(scopes.resolve(auth), value);
    }
    @GetMapping("/correspondences/{id}") SemanticCorrespondence correspondence(Authentication auth, @PathVariable String id) {
        return knowledge.correspondence(scopes.resolve(auth), id);
    }
    @PostMapping("/catalog/invalidate") int invalidate(Authentication auth, @RequestBody InvalidationEnvelope value) {
        return knowledge.invalidateSnapshot(scopes.resolve(auth), value.snapshotId());
    }
}
