package io.elmos.product.scmworkspace;

import org.junit.jupiter.api.Test;
import java.time.Instant;
import java.util.List;
import static io.elmos.product.scmworkspace.ScmWorkspaceModels.*;
import static org.junit.jupiter.api.Assertions.*;

class ScmWorkspaceAdmissionServiceTest {
    private final ScmWorkspaceAdmissionService service = new ScmWorkspaceAdmissionService();

    @Test void blocksUnknownCapabilitiesPersistentTokensAndIncompleteHydration() {
        var result = service.evaluate(request(List.of(new CapabilityClaim("rulesets", "3.17", "2026-03", false, false, false)), true, false));
        assertEquals(Decision.BLOCKED, result.decision());
        assertTrue(result.blockers().contains("CREDENTIAL_PERSISTENCE_FORBIDDEN"));
        assertTrue(result.blockers().contains("PARTIAL_CLONE_NOT_HYDRATED"));
        assertFalse(result.externalOperationExecuted());
    }

    @Test void completeEvidenceOnlyReachesExternalGate() {
        var result = service.evaluate(request(List.of(new CapabilityClaim("rulesets", "3.17", "2026-03", true, true, true)), false, true));
        assertEquals(Decision.READY_FOR_EXTERNAL_GATE, result.decision());
        assertFalse(result.certified()); assertFalse(result.pullRequestMerged());
    }

    private static AdmissionRequest request(List<CapabilityClaim> capabilities, boolean persisted, boolean complete) {
        return new AdmissionRequest("org", "ws", new RepositoryIdentity(Provider.GITHUB_ENTERPRISE_SERVER, "ghes-1", "42"),
                "a".repeat(40), "b".repeat(64), Instant.parse("2026-07-22T00:00:00Z"), capabilities,
                true, true, true, true, persisted, true, true, true, true, true, true, true,
                complete, true, true, true, List.of("evidence://workspace/manifest"));
    }
}
