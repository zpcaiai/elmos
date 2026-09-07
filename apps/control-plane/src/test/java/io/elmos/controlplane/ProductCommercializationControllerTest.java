package io.elmos.controlplane;

import io.elmos.product.assurance.EvidenceAssuranceModels.AdmissionRequest;
import io.elmos.product.policy.ContinuousAuthorizationModels.DecisionRequest;
import io.elmos.product.policy.ContinuousAuthorizationModels.PolicyDecision;
import io.elmos.product.policy.ContinuousAuthorizationModels.PolicyLanguage;
import io.elmos.product.scmworkspace.ScmWorkspaceModels.Provider;
import io.elmos.product.scmworkspace.ScmWorkspaceModels.RepositoryIdentity;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class ProductCommercializationControllerTest {
    private final ProductCommercializationController controller = new ProductCommercializationController();

    @Test void exposesSeparateProductNamespaceAndNotRunExternalEvidence() {
        var capabilities = controller.capabilities();
        assertEquals("Product Batch B35-B38", capabilities.get("namespace"));
        assertEquals("Migration Pack M35-M45", capabilities.get("migrationPackNamespace"));
        assertEquals("NOT_RUN", capabilities.get("externalExecutionEvidence"));
    }

    @Test void missingEvidenceIsBlockedAcrossScmAssuranceAndPolicy() {
        var scm = new io.elmos.product.scmworkspace.ScmWorkspaceModels.AdmissionRequest("org", "workspace",
                new RepositoryIdentity(Provider.GITHUB_CLOUD, "github.com", "42"), "a".repeat(40),
                "b".repeat(64), Instant.now(), List.of(), false, false, false, false, false,
                false, false, false, false, false, false, false, false, false, false, false, List.of());
        assertEquals("BLOCKED", controller.evaluateScm(scm).decision().name());

        var assurance = new AdmissionRequest("org", "pack", "a".repeat(64), "b".repeat(64), "producer", "judge",
                Instant.now(), false, false, false, false, false, false, false, false, false,
                List.of(), List.of(), false, false, true, true, false, false, false, false, List.of());
        assertEquals("BLOCKED", controller.evaluateAssurance(assurance).decision().name());

        var now = Instant.now();
        var policy = new DecisionRequest("org", "principal", "deploy", "service", "prod", "a".repeat(64),
                "b".repeat(64), "policy", "v1", "r1", "c".repeat(64), "engine", PolicyLanguage.CEL,
                now, now.plusSeconds(60), PolicyDecision.NOT_APPLICABLE, List.of(), List.of(), List.of(),
                false, false, false, false, false, false, false, false, false, false, false,
                false, false, false, false, false, false, false, false, false, false, false, false, List.of());
        assertEquals(PolicyDecision.DENY, controller.evaluatePolicy(policy).policyDecision());
    }
}
