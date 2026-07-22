package io.elmos.industrial;

import io.elmos.executiondomain.DomainDefinitions;
import io.elmos.executiondomain.EvidenceBoundDomainEngine;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class EdgeIotIndustrialEngineApplication {
    public static void main(String[] args) { SpringApplication.run(EdgeIotIndustrialEngineApplication.class, args); }
    @Bean EvidenceBoundDomainEngine domainEngine() { return new EvidenceBoundDomainEngine(DomainDefinitions.industrial()); }
}
