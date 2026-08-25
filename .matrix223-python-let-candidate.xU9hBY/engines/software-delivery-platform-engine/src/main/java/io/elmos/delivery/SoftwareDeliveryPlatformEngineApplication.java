package io.elmos.deliveryplatform;

import io.elmos.executiondomain.DomainDefinitions;
import io.elmos.executiondomain.EvidenceBoundDomainEngine;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class SoftwareDeliveryPlatformEngineApplication {
    public static void main(String[] args) { SpringApplication.run(SoftwareDeliveryPlatformEngineApplication.class, args); }
    @Bean EvidenceBoundDomainEngine domainEngine() { return new EvidenceBoundDomainEngine(DomainDefinitions.softwareDelivery()); }
}
