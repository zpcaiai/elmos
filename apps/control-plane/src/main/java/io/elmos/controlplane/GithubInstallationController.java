package io.elmos.controlplane;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

import java.net.URI;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/github/installations")
@ConditionalOnProperty(name = "elmos.github.app.enabled", havingValue = "true")
final class GithubInstallationController {
    record ConnectRequest(String connectionId) {}

    private final GithubInstallationOnboardingService service;

    GithubInstallationController(GithubInstallationOnboardingService service) {
        this.service = service;
    }

    @PostMapping("/connect")
    GithubInstallationOnboardingService.BeginResult connect(
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @RequestBody(required = false) ConnectRequest request
    ) {
        ControlPlanePrincipal.requireDatabaseBound(
                organizationId, "repository:write");
        return service.begin(organizationId, request == null ? null : request.connectionId());
    }

    @GetMapping("/setup")
    ResponseEntity<Void> setup(
            @RequestParam String state,
            @RequestParam("installation_id") long installationId,
            @RequestParam(name = "setup_action", required = false) String setupAction
    ) {
        if (setupAction != null && !setupAction.equals("install") && !setupAction.equals("update")) {
            throw new SecurityException("GitHub setup action is invalid");
        }
        GithubInstallationOnboardingService.SetupResult result =
                service.setup(state, installationId);
        return ResponseEntity.status(HttpStatus.SEE_OTHER)
                .location(URI.create(result.authorizationUrl()))
                .cacheControl(CacheControl.noStore())
                .build();
    }

    @GetMapping("/callback")
    ResponseEntity<Void> callback(
            @RequestParam String state,
            @RequestParam String code
    ) {
        GithubInstallationOnboardingService.Completion result =
                service.complete(state, code);
        return ResponseEntity.status(HttpStatus.SEE_OTHER)
                .location(URI.create(result.redirectUrl()))
                .cacheControl(CacheControl.noStore())
                .header("Referrer-Policy", "no-referrer")
                .build();
    }

    @ExceptionHandler(SecurityException.class)
    ResponseEntity<Map<String, Object>> forbidden(SecurityException ignored) {
        return ResponseEntity.status(HttpStatus.FORBIDDEN)
                .cacheControl(CacheControl.noStore())
                .body(Map.of(
                        "errorCode", "GITHUB_APP_ONBOARDING_DENIED",
                        "message", "GitHub App onboarding state or authority could not be verified.",
                        "retryable", false
                ));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<Map<String, Object>> invalid(IllegalArgumentException ignored) {
        return ResponseEntity.badRequest()
                .cacheControl(CacheControl.noStore())
                .body(Map.of(
                        "errorCode", "GITHUB_APP_ONBOARDING_INVALID",
                        "message", "GitHub App onboarding input is invalid.",
                        "retryable", false
                ));
    }
}
