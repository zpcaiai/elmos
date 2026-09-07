package io.elmos.operations;

import io.elmos.executiondomain.DomainDefinitions;
import io.elmos.executiondomain.EvidenceBoundDomainEngine;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OperationsSreItsmEngineApplication {
    public static void main(String[] args) { SpringApplication.run(OperationsSreItsmEngineApplication.class, args); }
    @Bean EvidenceBoundDomainEngine domainEngine() { return new EvidenceBoundDomainEngine(DomainDefinitions.operations()); }
}
