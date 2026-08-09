package io.elmos.legacy.web;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import io.elmos.legacy.service.LegacyOrderService;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

class LegacyOrderControllerTest {
    private static LocalValidatorFactoryBean validator;
    private static MockMvc mvc;

    @BeforeAll
    static void setUp() {
        validator = new LocalValidatorFactoryBean();
        validator.afterPropertiesSet();
        LegacyOrderController controller = new LegacyOrderController(new LegacyOrderService("CNY"));
        mvc = MockMvcBuilders.standaloneSetup(controller)
                .setControllerAdvice(new ApiExceptionHandler())
                .addInterceptors(new RequestAuditInterceptor())
                .setValidator(validator)
                .build();
    }

    @AfterAll
    static void closeValidator() {
        validator.close();
    }

    @Test
    void preservesJsonAndInterceptorContract() throws Exception {
        mvc.perform(get("/api/orders/42"))
                .andExpect(status().isOk())
                .andExpect(header().string("X-Legacy-Audit", "GET /api/orders/42"))
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.status").value("READY"))
                .andExpect(jsonPath("$.amountCents").value(5250))
                .andExpect(jsonPath("$.currency").value("CNY"));
    }

    @Test
    void preservesValidationErrorContract() throws Exception {
        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"customerId\":\"\",\"amountCents\":0}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
    }
}
