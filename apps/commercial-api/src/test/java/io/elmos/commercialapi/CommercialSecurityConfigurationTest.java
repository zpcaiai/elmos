package io.elmos.commercialapi;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;

@SpringBootTest
@AutoConfigureMockMvc
class CommercialSecurityConfigurationTest {
    @Autowired MockMvc mvc;

    @Test
    void publicCatalogRemainsReadableWhenIdentityIsNotConfigured() throws Exception {
        mvc.perform(get("/commercial/v1/pricing/catalog")).andExpect(status().isOk());
    }

    @Test
    void legacyMutationAndBillingRoutesFailClosedWithoutIdentity() throws Exception {
        mvc.perform(post("/commercial/v1/orders/fulfill")
                        .contentType("application/json")
                        .content("{}"))
                .andExpect(status().isUnauthorized());
        mvc.perform(get("/commercial/v1/billing/usage/current"))
                .andExpect(status().isUnauthorized());
        mvc.perform(post("/commercial/v1/orders/fulfill")
                        .with(jwt())
                        .contentType("application/json")
                        .content("{}"))
                .andExpect(status().isForbidden());
    }
}
