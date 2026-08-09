package io.elmos.workspaceservice;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static io.elmos.workspaceservice.SpringRuntimeModels.Action.START;
import static org.assertj.core.api.Assertions.assertThat;

class SpringRuntimeModelsTest {
    private final ObjectMapper json = new ObjectMapper();

    @Test
    void oldStartPayloadDefaultsToTheOriginalJava21Target() throws Exception {
        SpringRuntimeModels.Request restored = json.readValue("""
                {
                  "action":"START",
                  "runtimeId":"00000000-0000-0000-0000-000000000001",
                  "organizationId":"tenant-a",
                  "artifactRelativePath":"runs/one/application.jar",
                  "artifactSha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                  "healthCandidates":["/actuator/health"]
                }
                """, SpringRuntimeModels.Request.class);

        assertThat(restored.action()).isEqualTo(START);
        assertThat(restored.targetJava()).isEqualTo("21");
    }

    @Test
    void newStartPayloadPreservesTheExactJava17Target() throws Exception {
        SpringRuntimeModels.Request restored = json.readValue("""
                {
                  "action":"START",
                  "runtimeId":"00000000-0000-0000-0000-000000000001",
                  "organizationId":"tenant-a",
                  "artifactRelativePath":"runs/one/application.jar",
                  "artifactSha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                  "healthCandidates":["/actuator/health"],
                  "targetJava":"17"
                }
                """, SpringRuntimeModels.Request.class);

        assertThat(restored.targetJava()).isEqualTo("17");
    }
}
