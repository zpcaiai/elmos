package io.elmos.controlplane;

import io.elmos.scm.WebhookIngestionService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Arrays;
import java.util.List;
import java.util.Map;

@RestController
class GithubWebhookController {
    private final WebhookIngestionService ingestion; private final GithubWebhookSecrets secrets;
    GithubWebhookController(WebhookIngestionService ingestion, GithubWebhookSecrets secrets) { this.ingestion = ingestion; this.secrets = secrets; }

    @PostMapping(path = "/api/webhooks/github", consumes = "application/json")
    ResponseEntity<Map<String, String>> receive(@RequestHeader("X-GitHub-Delivery") String deliveryId,
                                                @RequestHeader("X-GitHub-Event") String eventType,
                                                @RequestHeader("X-Hub-Signature-256") String signature,
                                                @RequestBody byte[] rawBody) {
        List<char[]> active = secrets.active();
        try {
            var result = ingestion.ingest(deliveryId, eventType, signature, rawBody, active);
            return ResponseEntity.accepted().body(Map.of("status", result.name()));
        } finally { active.forEach(value -> Arrays.fill(value, '\0')); }
    }

    @ExceptionHandler(SecurityException.class) @ResponseStatus(HttpStatus.UNAUTHORIZED)
    Map<String, String> unauthorized() { return Map.of("code", "GITHUB_WEBHOOK_SIGNATURE_INVALID"); }
    @ExceptionHandler(IllegalArgumentException.class) @ResponseStatus(HttpStatus.BAD_REQUEST)
    Map<String, String> invalid() { return Map.of("code", "GITHUB_WEBHOOK_INVALID"); }
    @ExceptionHandler(IllegalStateException.class) @ResponseStatus(HttpStatus.SERVICE_UNAVAILABLE)
    Map<String, String> unavailable() { return Map.of("code", "GITHUB_WEBHOOK_NOT_CONFIGURED"); }
}
