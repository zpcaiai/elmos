package io.elmos.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.productionruntime.DeploymentToolExecutor;
import io.elmos.productionruntime.ProductionRuntimeModels.ToolCallRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.ToolCallReceipt;
import io.elmos.productionruntime.ProductionRuntimeModels.ToolCallStatus;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import java.nio.file.Path;
import java.nio.file.Files;
import java.nio.file.attribute.PosixFilePermission;
import java.util.Set;
import java.util.UUID;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.any;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

class DeploymentRuntimeControllerTest {
    @TempDir Path directory;

    @Test void workloadAuthenticationAndPendingOutcomeArePreserved() throws Exception {
        Path token = directory.resolve("token");
        Files.writeString(token, "deployment-test-workload-token-123456");
        try { Files.setPosixFilePermissions(token, Set.of(PosixFilePermission.OWNER_READ, PosixFilePermission.OWNER_WRITE)); }
        catch (UnsupportedOperationException ignored) {}
        var executor = mock(DeploymentToolExecutor.class);
        var mvc = MockMvcBuilders.standaloneSetup(new DeploymentRuntimeController(
                new ProductionRuntimeInternalAuthenticator(token), executor, request -> {}, request -> null)).build();
        var context = new ToolCallRequest(UUID.randomUUID(), UUID.randomUUID(), UUID.randomUUID(),
                UUID.randomUUID(), UUID.randomUUID(), UUID.randomUUID(), UUID.randomUUID(),
                "release-deployment:helm.render", "native-test",
                "sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a");
        byte[] body = new ObjectMapper().writeValueAsBytes(new DeploymentToolExecutor.Request(context, "helm.render", "{}".getBytes()));
        String route = "/internal/v1/production-runtime/deployment/tick";
        mvc.perform(post(route).contentType(MediaType.APPLICATION_JSON).content(body)).andExpect(status().isForbidden());
        verifyNoInteractions(executor);
        when(executor.tick(any())).thenReturn(new ToolCallReceipt(UUID.randomUUID(), ToolCallStatus.UNKNOWN, null, null));
        mvc.perform(post(route).header("Authorization", "Bearer deployment-test-workload-token-123456")
                .contentType(MediaType.APPLICATION_JSON).content(body)).andExpect(status().isAccepted())
                .andExpect(jsonPath("$.status").value("UNKNOWN"));
        when(executor.tick(any())).thenThrow(new SecurityException("secret diagnostic"));
        mvc.perform(post(route).header("Authorization", "Bearer deployment-test-workload-token-123456")
                .contentType(MediaType.APPLICATION_JSON).content(body)).andExpect(status().isForbidden())
                .andExpect(jsonPath("$.message").doesNotExist());
    }
}
