package io.elmos.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.delivery.DeliveryModels.ScmProvider;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class DeliveryControllerTest {
    @Test void scmPlanIsDraftAndSigningCapabilityFailsClosed() {
        var controller = new DeliveryController(new ObjectMapper());
        var plan = controller.scmPlan(new DeliveryController.ScmPlanRequest(ScmProvider.GITHUB, "acme/orders",
                "migration-1", "main", "head", "Modernize", "Evidence", List.of()));
        assertTrue(plan.draft()); assertFalse(plan.forcePush()); assertFalse(plan.autoMerge());
        assertEquals(Boolean.FALSE, controller.evidencePackCapability().get("configured"));
    }
}
