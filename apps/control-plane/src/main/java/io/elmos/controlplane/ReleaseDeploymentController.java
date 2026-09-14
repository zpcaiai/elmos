package io.elmos.controlplane;

import jakarta.servlet.http.HttpServletRequest;
import java.io.IOException;
import java.util.Map;
import java.util.Set;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

/** Authenticated deployment mount. No request field supplies host scope or grants. */
@RestController
final class ReleaseDeploymentController {
    interface Host {
        Binding binding(String environment);
        HostResponse exchange(String method, String path, byte[] body, String actor, Binding binding);
    }

    record HostResponse(int status, byte[] body) {
        HostResponse {
            if (status != 200 && status != 202) throw new IllegalArgumentException("DEPLOYMENT_HOST_STATUS");
            body = body.clone();
        }
        @Override public byte[] body() { return body.clone(); }
    }

    record Binding(Map<String, String> scope, Map<String, Set<String>> actorPermissions) {
        Binding {
            scope = Map.copyOf(scope);
            actorPermissions = actorPermissions.entrySet().stream().collect(
                    java.util.stream.Collectors.toUnmodifiableMap(Map.Entry::getKey,
                            entry -> Set.copyOf(entry.getValue())));
            if (!scope.keySet().equals(Set.of("tenant_id", "workspace_id", "project_id",
                                              "environment_id", "account_id"))
                    || scope.values().stream().anyMatch(value ->
                        !value.matches("[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}"))) {
                throw new IllegalArgumentException("DEPLOYMENT_BINDING_INVALID");
            }
        }
    }

    private final ObjectProvider<Host> hosts;
    ReleaseDeploymentController(ObjectProvider<Host> hosts) { this.hosts = hosts; }

    @RequestMapping(value = "/api/v1/release-deployment/{environment}/**",
                    method = {RequestMethod.GET, RequestMethod.POST})
    ResponseEntity<byte[]> call(@PathVariable String environment, HttpServletRequest request) throws IOException {
        Host host = hosts.getIfAvailable();
        if (host == null) throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
                "DEPLOYMENT_HOST_NOT_CONFIGURED");
        Binding binding = host.binding(environment);
        if (binding == null || !binding.scope().get("environment_id").equals(environment)) {
            throw new AccessDeniedException("DEPLOYMENT_ENVIRONMENT_NOT_BOUND");
        }
        var principal = ControlPlanePrincipal.requireDatabaseBound(binding.scope().get("tenant_id"), "workspace:view");
        if (!binding.actorPermissions().containsKey(principal.actorId())) {
            throw new AccessDeniedException("DEPLOYMENT_ACTOR_NOT_GRANTED");
        }
        String prefix = request.getContextPath() + "/api/v1/release-deployment/" + environment;
        String uri = request.getRequestURI();
        if (!uri.startsWith(prefix + "/v1/") || uri.contains("%") || uri.contains("..")
                || request.getQueryString() != null || request.getHeader("Transfer-Encoding") != null
                || request.getHeader("Content-Encoding") != null) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "DEPLOYMENT_REQUEST_INVALID");
        }
        if (request.getMethod().equals("POST") && (request.getContentType() == null
                || !request.getContentType().split(";", 2)[0].trim().equals("application/json"))) {
            throw new ResponseStatusException(HttpStatus.UNSUPPORTED_MEDIA_TYPE);
        }
        byte[] body = request.getInputStream().readNBytes(65537);
        if (body.length > 65536) throw new ResponseStatusException(HttpStatus.PAYLOAD_TOO_LARGE);
        HostResponse result = host.exchange(request.getMethod(), uri.substring(prefix.length()), body,
                                     principal.actorId(), binding);
        return ResponseEntity.status(result.status()).header("Content-Type", "application/json")
                .header("Cache-Control", "no-store").header("X-Content-Type-Options", "nosniff").body(result.body());
    }
}
