package io.elmos.controlplane;

import io.elmos.proofloop.ModernizationProofLoopEngine;
import io.elmos.proofloop.ProofLoopModels;
import io.elmos.proofloop.SkillContractCatalog;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

/** Read-only discovery and subject binding API; execution is submitted through the durable job endpoint. */
@RestController
@RequestMapping("/api/v1/modernization-proof")
class ModernizationProofContractController {
    private final SkillContractCatalog catalog;
    private final ModernizationProofLoopEngine engine;

    ModernizationProofContractController(SkillContractCatalog catalog, ModernizationProofLoopEngine engine) {
        this.catalog = catalog;
        this.engine = engine;
    }

    @GetMapping("/contracts")
    List<Map<String, Object>> contracts() {
        principal();
        return catalog.all().stream().map(contract -> Map.<String, Object>of(
                "id", contract.id(),
                "batch", contract.batch(),
                "name", contract.name(),
                "dependencies", contract.dependencies(),
                "canonicalSha256", contract.canonicalSha256(),
                "executionClass", contract.executionClass().name(),
                "evidenceSlots", contract.evidence())).toList();
    }

    record SubjectDigestRequest(
            String projectId,
            String repositoryId,
            String baselineCommit,
            String candidateCommit,
            String imageDigest,
            String policyDigest
    ) {}

    @PostMapping("/subject-digest")
    Map<String, Object> subjectDigest(@RequestBody SubjectDigestRequest request) {
        ControlPlanePrincipal principal = principal();
        ProofLoopModels.Subject subject = new ProofLoopModels.Subject(
                principal.organizationId(), request.projectId(), request.repositoryId(), request.baselineCommit(),
                request.candidateCommit(), request.imageDigest(), request.policyDigest());
        return Map.of(
                "organizationId", principal.organizationId(),
                "subjectDigest", engine.subjectDigest(subject),
                "canonicalizationVersion", 1);
    }

    private static ControlPlanePrincipal principal() {
        ControlPlanePrincipal principal = ControlPlanePrincipal.current()
                .orElseThrow(() -> new AccessDeniedException("CONTROL_PLANE_AUTH_REQUIRED"));
        principal.require(principal.organizationId(), principal.actorId(), "modernization:execute");
        return principal;
    }
}
