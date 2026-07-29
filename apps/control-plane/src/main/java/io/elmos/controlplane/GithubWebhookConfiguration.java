package io.elmos.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.scm.GithubWebhookVerifier;
import io.elmos.scm.WebhookIngestionService;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.web.servlet.FilterRegistrationBean;

import java.time.Clock;
import java.util.ArrayList;
import java.util.List;

@Configuration
class GithubWebhookConfiguration {
    @Bean WebhookIngestionService webhookIngestionService(GithubWebhookVerifier verifier,
            WebhookIngestionService.DeliveryStore store,
            ObjectMapper objectMapper, Clock clock,
            @Value("${elmos.github.webhook.max-body-bytes:1048576}") int maxBodyBytes) {
        return new WebhookIngestionService(verifier, store, objectMapper, clock, maxBodyBytes);
    }
    @Bean GithubWebhookVerifier githubWebhookVerifier() { return new GithubWebhookVerifier(); }
    @Bean FilterRegistrationBean<GithubWebhookBodyLimitFilter> githubWebhookBodyLimit(
            @Value("${elmos.github.webhook.max-body-bytes:1048576}") int maxBodyBytes) {
        var registration = new FilterRegistrationBean<>(new GithubWebhookBodyLimitFilter(maxBodyBytes));
        registration.addUrlPatterns("/api/webhooks/github"); registration.setOrder(Integer.MIN_VALUE + 100); return registration;
    }
    @Bean GithubWebhookSecrets githubWebhookSecrets(
            @Value("${elmos.github.webhook.secret:}") String current,
            @Value("${elmos.github.webhook.previous-secret:}") String previous,
            @Value("${elmos.github.webhook.secret-file:}") String currentFile,
            @Value("${elmos.github.webhook.previous-secret-file:}") String previousFile,
            @Value("${ELMOS_ENVIRONMENT:development}") String environment) {
        boolean production = environment.equalsIgnoreCase("production")
                || environment.equalsIgnoreCase("prod");
        if (production && (!current.isBlank() || !previous.isBlank())) {
            throw new IllegalStateException(
                    "GitHub webhook secrets must be file-backed in production");
        }
        return () -> {
            String active = currentFile.isBlank()
                    ? current
                    : OwnerOnlySecretFile.readRequired(
                            currentFile, 32, 4096,
                            "GITHUB_WEBHOOK_SECRET_FILE_INVALID");
            String retiring = previousFile.isBlank()
                    ? previous
                    : OwnerOnlySecretFile.readOptional(
                            previousFile, 32, 4096,
                            "GITHUB_WEBHOOK_PREVIOUS_SECRET_FILE_INVALID");
            if (active.isBlank()) {
                throw new IllegalStateException(
                        "GitHub webhook secret is not configured");
            }
            List<char[]> values = new ArrayList<>();
            values.add(active.toCharArray());
            if (!retiring.isBlank()) {
                values.add(retiring.toCharArray());
            }
            return values;
        };
    }
}
