package io.elmos.controlplane;

import io.elmos.productionruntime.DeploymentToolExecutor;
import io.elmos.productionruntime.ProductionRuntimeModels.ToolCallStatus;
import org.springframework.boot.autoconfigure.condition.ConditionalOnExpression;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import java.util.Map;

@RestController
@RequestMapping("/internal/v1/production-runtime/deployment")
@ConditionalOnProperty(name = "elmos.release-deployment.runtime-enabled", havingValue = "true")
@ConditionalOnExpression("'${component:scheduler}' == 'billing'")
class DeploymentRuntimeController {
    private final ProductionRuntimeInternalAuthenticator authenticator;
    private final DeploymentToolExecutor executor;
    private final DeploymentToolExecutor.Authorization authorization;
    private final DeploymentToolExecutor.ReceiptLookup lookup;

    DeploymentRuntimeController(ProductionRuntimeInternalAuthenticator authenticator, DeploymentToolExecutor executor,
                                DeploymentToolExecutor.Authorization authorization, DeploymentToolExecutor.ReceiptLookup lookup) {
        this.authenticator = authenticator;
        this.executor = executor;
        this.authorization = authorization;
        this.lookup = lookup;
    }

    @PostMapping("/lookup")
    ResponseEntity<?> lookup(@RequestHeader(name = "Authorization", required = false) String token,
                             @RequestBody DeploymentToolExecutor.Request request) {
        authenticator.require(token);
        authorization.require(request);
        var receipt = lookup.find(request.context());
        return ResponseEntity.ok().header("Cache-Control", "no-store").body(
                receipt == null ? Map.of("status", "NOT_FOUND") : receipt);
    }

    @PostMapping("/tick")
    ResponseEntity<?> tick(@RequestHeader(name = "Authorization", required = false) String authorization,
                           @RequestBody DeploymentToolExecutor.Request request) {
        authenticator.require(authorization);
        // The workload token authenticates the service only. The executor must
        // separately validate the current tenant/resource capability before lookup or dispatch.
        var receipt = executor.tick(request);
        int status = receipt.status() == ToolCallStatus.COMPLETE ? 200
                : receipt.status() == ToolCallStatus.FAILED ? 422 : 202;
        return ResponseEntity.status(status).header("Cache-Control", "no-store").body(receipt);
    }

    @ExceptionHandler(AccessDeniedException.class)
    ResponseEntity<?> denied() {
        return ResponseEntity.status(403).body(Map.of("code", "DEPLOYMENT_WORKLOAD_AUTH_REQUIRED"));
    }

    @ExceptionHandler({IllegalArgumentException.class, SecurityException.class})
    ResponseEntity<?> rejected() {
        return ResponseEntity.status(403).body(Map.of("code", "DEPLOYMENT_REQUEST_REJECTED"));
    }
}
