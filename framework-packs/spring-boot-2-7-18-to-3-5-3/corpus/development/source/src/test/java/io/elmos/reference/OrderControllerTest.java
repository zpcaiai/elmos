package io.elmos.reference;

import static org.hamcrest.Matchers.is;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void preservesOrderContract() throws Exception {
        mvc.perform(get("/api/orders/42")
                .with(SecurityMockMvcRequestPostProcessors.httpBasic("operator", "operator-password")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id", is(42)))
            .andExpect(jsonPath("$.status", is("READY")))
            .andExpect(jsonPath("$.amountCents", is(5250)));
    }

    @Test
    void rejectsUnauthenticatedOrderReads() throws Exception {
        mvc.perform(get("/api/orders/42"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void preservesValidationContract() throws Exception {
        mvc.perform(post("/api/orders")
                .with(SecurityMockMvcRequestPostProcessors.httpBasic("operator", "operator-password"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"customerId\":\"\"}"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void acceptsAuthenticatedValidOrder() throws Exception {
        mvc.perform(post("/api/orders")
                .with(SecurityMockMvcRequestPostProcessors.httpBasic("operator", "operator-password"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"customerId\":\"customer-42\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.customerId", is("customer-42")))
            .andExpect(jsonPath("$.status", is("CREATED")));
    }
}
