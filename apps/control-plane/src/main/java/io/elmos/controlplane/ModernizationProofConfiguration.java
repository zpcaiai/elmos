package io.elmos.controlplane;

import io.elmos.proofloop.ModernizationProofLoopEngine;
import io.elmos.proofloop.ProofLoopOperators;
import io.elmos.proofloop.SkillContractCatalog;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** Immutable Batch 105-108 contract kernel configuration. */
@Configuration
class ModernizationProofConfiguration {
    @Bean
    SkillContractCatalog modernizationProofContractCatalog() {
        return new SkillContractCatalog();
    }

    @Bean
    ModernizationProofLoopEngine modernizationProofLoopEngine(SkillContractCatalog catalog) {
        return new ModernizationProofLoopEngine(
                catalog, new ProofLoopOperators(), new com.fasterxml.jackson.databind.ObjectMapper(),
                java.time.Clock.systemUTC());
    }
}
