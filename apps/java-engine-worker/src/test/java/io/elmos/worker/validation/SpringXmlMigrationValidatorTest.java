package io.elmos.worker.validation;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class SpringXmlMigrationValidatorTest {

    @TempDir
    Path tempDir;

    private final SpringXmlMigrationValidator validator = new SpringXmlMigrationValidator();

    @Test
    void testDetectsUnmigratedXmlBeans() throws IOException {
        Path xmlFile = tempDir.resolve("applicationContext.xml");
        Files.writeString(xmlFile, """
                <?xml version="1.0" encoding="UTF-8"?>
                <beans xmlns="http://www.springframework.org/schema/beans"
                       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                       xsi:schemaLocation="http://www.springframework.org/schema/beans http://www.springframework.org/schema/beans/spring-beans.xsd">
                    <bean id="orderService" class="com.example.OrderService"/>
                    <bean id="paymentService" class="com.example.PaymentService"/>
                </beans>
                """);

        // Only orderService is defined in JavaConfig
        Path javaFile = tempDir.resolve("AppConfig.java");
        Files.writeString(javaFile, """
                package com.example;
                import org.springframework.context.annotation.Bean;
                import org.springframework.context.annotation.Configuration;

                @Configuration
                public class AppConfig {
                    @Bean
                    public OrderService orderService() { return new OrderService(); }
                }
                """);

        SpringXmlMigrationValidator.XmlMigrationAuditReport report = validator.auditProject(tempDir);
        assertEquals(2, report.totalBeansInXml());
        assertEquals(1, report.migratedBeansFound());
        assertEquals(50.0, report.migrationCompletenessRate());
        assertFalse(report.isFullyMigrated());
        assertTrue(report.violations().stream().anyMatch(v -> "XML-001".equals(v.ruleId()) && v.beanOrTagId().equalsIgnoreCase("paymentService")));
    }

    @Test
    void testFullyMigratedXmlBeans() throws IOException {
        Path xmlFile = tempDir.resolve("beans.xml");
        Files.writeString(xmlFile, """
                <?xml version="1.0" encoding="UTF-8"?>
                <beans xmlns="http://www.springframework.org/schema/beans"
                       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                       xsi:schemaLocation="http://www.springframework.org/schema/beans http://www.springframework.org/schema/beans/spring-beans.xsd">
                    <bean id="myService" class="com.example.MyService"/>
                </beans>
                """);

        Path javaFile = tempDir.resolve("MyConfig.java");
        Files.writeString(javaFile, """
                package com.example;
                import org.springframework.context.annotation.Bean;
                import org.springframework.context.annotation.Configuration;

                @Configuration
                public class MyConfig {
                    @Bean
                    public MyService myService() { return new MyService(); }
                }
                """);

        SpringXmlMigrationValidator.XmlMigrationAuditReport report = validator.auditProject(tempDir);
        assertEquals(1, report.totalBeansInXml());
        assertEquals(1, report.migratedBeansFound());
        assertEquals(100.0, report.migrationCompletenessRate());
        assertTrue(report.isFullyMigrated());
    }
}
