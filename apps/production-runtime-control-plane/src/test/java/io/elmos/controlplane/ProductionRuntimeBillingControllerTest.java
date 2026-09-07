package io.elmos.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.productionruntime.JdbcProductionProviderPayloadStore;
import io.elmos.productionruntime.ProductionBillingPort;
import io.elmos.productionruntime.ProductionModelCallExecutor;
import io.elmos.productionruntime.ProductionModelProviderRegistry;
import io.elmos.productionruntime.ProductionRuntimeModels.ToolCallReceipt;
import io.elmos.productionruntime.ProductionRuntimeModels.ToolCallRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.ToolCallStatus;
import io.elmos.productionruntime.ProductionRuntimeModels.TopUpRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.TopUpResult;
import io.elmos.productionruntime.ProductionRuntimeModels.TopUpStatus;
import io.elmos.productionruntime.ProductionToolCallPort;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.beans.factory.support.StaticListableBeanFactory;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.math.BigDecimal;
import java.util.Set;
import java.util.UUID;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class ProductionRuntimeBillingControllerTest {
    private static final String WORKLOAD_TOKEN = "billing-controller-workload-token-1234";
    private static final String TOPUP_TOKEN = "billing-controller-topup-token-5678";

    @TempDir
    Path temporary;

    private MockMvc mvc;
    private ObjectMapper json;
    private ToolCallRequest request;
    private TopUpRequest topUp;

    @BeforeEach
    void setUp() throws Exception {
        Path workloadToken = credential("workload-token", WORKLOAD_TOKEN);
        Path topUpToken = credential("topup-token", TOPUP_TOKEN);
        ProductionToolCallPort tools = mock(ProductionToolCallPort.class);
        UUID toolCallId = UUID.randomUUID();
        when(tools.begin(any())).thenReturn(new ToolCallReceipt(
                toolCallId, ToolCallStatus.CREATED, null, null));
        ProductionBillingPort billing = mock(ProductionBillingPort.class);
        when(billing.applyVerifiedTopUp(any())).thenReturn(new TopUpResult(
                UUID.randomUUID(), TopUpStatus.COMPLETED, new BigDecimal("10.000000000000")));
        StaticListableBeanFactory providers = new StaticListableBeanFactory();
        var controller = new ProductionRuntimeBillingController(
                new ProductionRuntimeInternalAuthenticator(workloadToken),
                new ProductionRuntimeTopUpAuthenticator(topUpToken),
                billing,
                mock(JdbcProductionProviderPayloadStore.class),
                mock(ProductionModelCallExecutor.class),
                tools,
                providers.getBeanProvider(ProductionModelProviderRegistry.class));
        mvc = MockMvcBuilders.standaloneSetup(controller).build();
        json = new ObjectMapper();
        request = new ToolCallRequest(
                UUID.randomUUID(), UUID.randomUUID(), UUID.randomUUID(),
                UUID.randomUUID(), UUID.randomUUID(), UUID.randomUUID(),
                UUID.randomUUID(), "compiler", "tool-key", "request-hash");
        topUp = new TopUpRequest(
                UUID.randomUUID(), UUID.randomUUID(), "stripe", "payment-123",
                BigDecimal.ONE, "topup-request-hash");
    }

    @Test
    void toolCallApiIsAuthenticatedAndReturnsDistinctReceipt() throws Exception {
        mvc.perform(post("/internal/v1/production-runtime/billing/tool-calls")
                        .header("Authorization", "Bearer " + WORKLOAD_TOKEN)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json.writeValueAsBytes(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("CREATED"));

        mvc.perform(post("/internal/v1/production-runtime/billing/tool-calls")
                        .header("Authorization", "Bearer wrong")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json.writeValueAsBytes(request)))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("UNAUTHORIZED"))
                .andExpect(jsonPath("$.message").doesNotExist());
    }

    @Test
    void topUpAuthorityIsNotInterchangeableWithWorkloadAuthority() throws Exception {
        mvc.perform(post("/internal/v1/production-runtime/billing/topups")
                        .header("Authorization", "Bearer " + WORKLOAD_TOKEN)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json.writeValueAsBytes(topUp)))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("UNAUTHORIZED"))
                .andExpect(jsonPath("$.message").doesNotExist());

        mvc.perform(post("/internal/v1/production-runtime/billing/topups")
                        .header("Authorization", "Bearer " + TOPUP_TOKEN)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json.writeValueAsBytes(topUp)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("COMPLETED"));

        mvc.perform(post("/internal/v1/production-runtime/billing/tool-calls")
                        .header("Authorization", "Bearer " + TOPUP_TOKEN)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json.writeValueAsBytes(request)))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("UNAUTHORIZED"))
                .andExpect(jsonPath("$.message").doesNotExist());
    }

    private Path credential(String name, String value) throws Exception {
        Path token = temporary.resolve(name);
        Files.writeString(token, value);
        try {
            Files.setPosixFilePermissions(token, Set.of(
                    PosixFilePermission.OWNER_READ,
                    PosixFilePermission.OWNER_WRITE));
        } catch (UnsupportedOperationException ignored) {
            // The production credential reader applies the platform ACL check.
        }
        return token;
    }
}
