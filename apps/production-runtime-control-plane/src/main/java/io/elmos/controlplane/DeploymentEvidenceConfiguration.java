package io.elmos.controlplane;

import io.elmos.cas.TenantCasStore;
import java.time.Clock;
import org.springframework.boot.autoconfigure.condition.ConditionalOnExpression;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@ConditionalOnProperty(name={"elmos.release-deployment.runtime-enabled","elmos.release-deployment.evidence-enabled"},havingValue="true")
@ConditionalOnExpression("'${component:scheduler}' == 'billing'")
class DeploymentEvidenceConfiguration {
    @Bean
    DeploymentCasEvidenceVerifier deploymentCasEvidenceVerifier(TenantCasStore cas,
            DeploymentCasEvidenceVerifier.Bindings bindings, DeploymentCasEvidenceVerifier.Trust trust) {
        return new DeploymentCasEvidenceVerifier(cas,bindings,trust,Clock.systemUTC());
    }
}
