package io.elmos.workspaceservice;

import io.elmos.secret.SecretInjectionService;
import io.elmos.secret.SecretLease;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.time.Duration;

@RestController
@ConditionalOnBean(SecretInjectionService.class)
@RequestMapping("/api/v1/workspaces/{workspaceId}/secrets")
final class SecretInjectionController {
    record InjectionRequest(String leaseId, SecretLease.SecretType type, long ttlSeconds){}
    private final SecretInjectionService secrets;
    SecretInjectionController(SecretInjectionService secrets){this.secrets=secrets;}
    @PostMapping @ResponseStatus(HttpStatus.CREATED) SecretLease inject(@PathVariable String workspaceId,@RequestBody InjectionRequest request){
        if(request.leaseId()==null||!request.leaseId().matches("[A-Za-z0-9._:-]{1,64}")||request.type()==null)throw new IllegalArgumentException("secret request identity is invalid");
        return secrets.inject(request.leaseId(),new SecretInjectionService.SecretRequest(workspaceId,request.type(),Duration.ofSeconds(request.ttlSeconds())));
    }
    @DeleteMapping("/{leaseId}") @ResponseStatus(HttpStatus.NO_CONTENT) void revoke(@PathVariable String workspaceId,@PathVariable String leaseId){secrets.revoke(leaseId,workspaceId);}
}
