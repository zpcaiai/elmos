package io.elmos.commercialapi;

import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.test.web.servlet.MockMvc;

import java.util.UUID;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "ELMOS_TRIAL_IDENTITY_PEPPER=0123456789abcdef0123456789abcdef",
        "elmos.billing.live-enabled=false"
})
@AutoConfigureMockMvc
@EnabledIfEnvironmentVariable(named = "ELMOS_COMMERCIAL_DATABASE_URL", matches = "jdbc:postgresql:.*")
class SelfServiceBillingApiLiveTest {
    @Autowired MockMvc mvc;

    @Test
    void derivesOrganizationFromJwtAndEnforcesExactScopes() throws Exception {
        Assumptions.assumeTrue("true".equals(
                System.getenv("ELMOS_BILLING_TEST_DISPOSABLE_CONFIRMED")));
        String suffix = UUID.randomUUID().toString();
        String organization = "billing-api-it-" + suffix;
        String actor = "actor-" + suffix;
        var fixtureJdbc = JdbcClient.create(new DriverManagerDataSource(
                System.getenv("ELMOS_BILLING_TEST_JDBC_URL"),
                System.getenv("ELMOS_BILLING_TEST_DATABASE_USERNAME"),
                System.getenv("ELMOS_BILLING_TEST_DATABASE_PASSWORD")
        ));
        fixtureJdbc.sql("""
                insert into organizations(organization_id, display_name, status)
                values (:organization, 'Billing API integration test', 'ACTIVE')
                """).param("organization", organization).update();

        mvc.perform(get("/actuator/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));

        mvc.perform(post("/commercial/v1/billing/trial")
                        .with(accountJwt(organization, actor, "commercial:usage:read"))
                        .header("Idempotency-Key", "trial-api-denied-" + suffix))
                .andExpect(status().isForbidden());

        mvc.perform(post("/commercial/v1/billing/trial")
                        .with(accountJwt(
                                organization, actor,
                                "commercial:billing:write commercial:usage:read"))
                        .header("Idempotency-Key", "trial-api-" + suffix)
                        .header("X-ELMOS-Organization", "attacker-org"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.planId").value("elmos-free-trial"))
                .andExpect(jsonPath("$.status").value("ACTIVE"));

        mvc.perform(get("/commercial/v1/billing/usage/current")
                        .with(accountJwt(organization, actor, "commercial:usage:read"))
                        .header("X-ELMOS-Organization", "attacker-org"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.organizationId").value(organization))
                .andExpect(jsonPath("$.actorId").value(actor))
                .andExpect(jsonPath("$.planId").value("elmos-free-trial"))
                .andExpect(jsonPath("$.tokens.consumed").value(0))
                .andExpect(jsonPath("$.credits.consumed").value(0));

        mvc.perform(get("/commercial/v1/billing/subscriptions/current")
                        .with(accountJwt(organization, actor, "commercial:usage:read")))
                .andExpect(status().isForbidden());

        mvc.perform(get("/commercial/v1/billing/subscriptions/current")
                        .with(accountJwt(organization, actor, "commercial:billing:write"))
                        .header("X-ELMOS-Organization", "attacker-org"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.planId").value("elmos-free-trial"))
                .andExpect(jsonPath("$.status").value("TRIALING"))
                .andExpect(jsonPath("$.cancelAtPeriodEnd").value(false))
                .andExpect(jsonPath("$.canCancel").value(false))
                .andExpect(jsonPath("$.providerSubscriptionRef").doesNotExist())
                .andExpect(jsonPath("$.organizationId").doesNotExist());
    }

    private static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.JwtRequestPostProcessor accountJwt(
            String organization,
            String actor,
            String scopes
    ) {
        return jwt().jwt(builder -> builder
                .issuer("https://identity.example")
                .subject(actor)
                .claim("organization_id", organization)
                .claim("scope", scopes)
                .claim("email", actor + "@example.test")
                .claim("email_verified", true));
    }
}
