package io.elmos.fixtures;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerTest {
    @Autowired MockMvc http;

    @Test void preservesPingContract() throws Exception {
        http.perform(get("/orders/ping"))
                .andExpect(status().isOk())
                .andExpect(content().json("{\"status\":\"legacy-ok\"}"));
    }

    @Test void rejectsBlankCustomerAndCreatesValidOrder() throws Exception {
        http.perform(post("/orders").contentType("application/json").content("{\"customerId\":\"\"}"))
                .andExpect(status().isBadRequest());
        http.perform(post("/orders").contentType("application/json").content("{\"customerId\":\"customer\"}"))
                .andExpect(status().isCreated())
                .andExpect(content().json("{\"orderId\":\"customer-001\"}"));
    }
}
