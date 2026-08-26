package io.elmos.worker;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import javax.xml.parsers.DocumentBuilderFactory;
import java.io.ByteArrayInputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

import static io.elmos.worker.SpringCapabilityFingerprint.EvidenceState.CONDITIONAL;
import static io.elmos.worker.SpringCapabilityFingerprint.EvidenceState.DECLARED_ONLY;
import static io.elmos.worker.SpringCapabilityFingerprint.EvidenceState.OBSERVED;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringCapabilityFingerprintTest {
    @TempDir Path temporaryDirectory;

    @Test void dependenciesRemainDeclaredOnlyUntilProductionUseIsTraced() throws Exception {
        String pom = """
                <project>
                  <dependencies>
                    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-security</artifactId></dependency>
                    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-data-jpa</artifactId></dependency>
                    <dependency><groupId>org.hibernate.orm</groupId><artifactId>hibernate-core</artifactId></dependency>
                    <dependency><groupId>org.postgresql</groupId><artifactId>postgresql</artifactId></dependency>
                    <dependency><groupId>org.springframework</groupId><artifactId>spring-tx</artifactId></dependency>
                    <dependency><groupId>org.springframework.kafka</groupId><artifactId>spring-kafka</artifactId></dependency>
                    <dependency><groupId>org.springframework.amqp</groupId><artifactId>spring-rabbit</artifactId></dependency>
                    <dependency><groupId>org.springframework</groupId><artifactId>spring-jms</artifactId></dependency>
                    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-cache</artifactId></dependency>
                    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-quartz</artifactId></dependency>
                    <dependency><groupId>org.springframework</groupId><artifactId>spring-webmvc</artifactId></dependency>
                  </dependencies>
                </project>
                """;
        Files.writeString(temporaryDirectory.resolve("pom.xml"), pom);

        SpringCapabilityFingerprint.Analysis analysis =
                SpringCapabilityFingerprint.analyze(temporaryDirectory, pom, "pom.xml");
        Map<String, SpringCapabilityFingerprint.CapabilityFact> facts = factsById(analysis);

        assertTrue(analysis.activeCapabilities().isEmpty());
        for (String capability : List.of(
                "security", "persistence-jpa", "persistence-provider-hibernate",
                "database-provider-postgresql", "transactions", "messaging-kafka",
                "messaging-rabbit", "messaging-jms", "cache", "scheduler", "spring-mvc")) {
            assertEquals(DECLARED_ONLY, facts.get(capability).state(), capability);
            assertTrue(analysis.unknowns().contains(
                    "declared-only-capability-runtime-activation-unobserved:" + capability));
        }

        SpringUpgradeModels.Fingerprint enriched = SpringCapabilityFingerprint.enrich(
                new SpringUpgradeModels.Fingerprint(
                        "2.7.18", "17", "maven", List.of(), List.of("spring-boot-parent"),
                        List.of(), Map.of("spring-boot-parent", List.of("pom.xml:spring-boot-starter-parent"))),
                analysis);
        assertFalse(enriched.activeCapabilities().contains("security"));
        assertTrue(enriched.sourceTraces().get("security").stream()
                .allMatch(trace -> trace.startsWith("declared-only|")));

        Map<String, Map<String, Object>> contracts = fcmById(enriched);
        assertEquals("declared-only", contracts.get("security").get("status"));
        assertEquals("low-declaration-only", contracts.get("security").get("confidence"));
        assertEquals(false, contracts.get("security").get("runtime_confirmation"));
        assertTrue(list(contracts.get("security").get("obligations"))
                .contains("preserve-filter-chain-order"));
    }

    @Test void classifiesComplexCapabilitiesWithConditionsProvidersAndSourceLines() throws Exception {
        String pom = """
                <project><dependencies>
                  <dependency><artifactId>spring-boot-starter-security</artifactId></dependency>
                  <dependency><artifactId>spring-boot-starter-data-jpa</artifactId></dependency>
                  <dependency><artifactId>hibernate-core</artifactId></dependency>
                  <dependency><artifactId>postgresql</artifactId></dependency>
                  <dependency><artifactId>spring-kafka</artifactId></dependency>
                </dependencies></project>
                """;
        Files.writeString(temporaryDirectory.resolve("pom.xml"), pom);
        write("src/main/java/example/SecurityConfig.java", """
                package example;
                @Profile("prod")
                @EnableWebSecurity
                final class SecurityConfig {
                    SecurityFilterChain chain(HttpSecurity http) throws Exception {
                        http.authorizeHttpRequests(auth -> auth.requestMatchers("/admin/**").hasRole("ADMIN"))
                                .httpBasic();
                        return http.build();
                    }
                    AuthenticationProvider authenticationProvider() { return null; }
                }
                """);
        write("src/main/java/example/Account.java", """
                package example;
                @Entity
                final class Account { }
                interface AccountRepository extends JpaRepository<Account, Long> { }
                """);
        write("src/main/java/example/Workflows.java", """
                package example;
                final class Workflows {
                    @Transactional(rollbackFor = Exception.class)
                    void bill() { }
                    @KafkaListener(topics = "billing") void kafka(String value) { }
                    @RabbitListener(queues = "billing") void rabbit(String value) { }
                    @JmsListener(destination = "billing") void jms(String value) { }
                    @Cacheable(cacheNames = "accounts", key = "#id") String cached(String id) { return id; }
                    @Scheduled(cron = "${billing.cron}") void schedule() { }
                }
                """);
        write("src/main/java/example/LegacyInitializer.java", """
                package example;
                final class LegacyInitializer implements WebApplicationInitializer {
                    void register() { DispatcherServlet servlet = new DispatcherServlet(); }
                }
                """);
        write("src/main/java/example/DynamicBeans.java", """
                package example;
                final class DynamicBeans implements BeanDefinitionRegistryPostProcessor { }
                """);
        write("src/main/resources/application-prod.yml", """
                spring:
                  datasource:
                    url: jdbc:postgresql://${DB_HOST}/billing
                """);
        write("src/main/resources/web-context.xml", """
                <beans xmlns:mvc="http://www.springframework.org/schema/mvc"
                       xmlns:context="http://www.springframework.org/schema/context">
                  <mvc:annotation-driven/>
                  <context:component-scan base-package="example"/>
                </beans>
                """);
        write("src/main/webapp/WEB-INF/web.xml", """
                <web-app>
                  <servlet>
                    <servlet-name>dispatcher</servlet-name>
                    <servlet-class>org.springframework.web.servlet.DispatcherServlet</servlet-class>
                  </servlet>
                </web-app>
                """);

        SpringCapabilityFingerprint.Analysis analysis =
                SpringCapabilityFingerprint.analyze(temporaryDirectory, pom, "pom.xml");
        Map<String, SpringCapabilityFingerprint.CapabilityFact> facts = factsById(analysis);

        assertEquals(CONDITIONAL, facts.get("security").state());
        assertEquals(CONDITIONAL, facts.get("authentication").state());
        assertEquals(CONDITIONAL, facts.get("authorization").state());
        assertFalse(analysis.activeCapabilities().contains("security"));
        assertTrue(analysis.unknowns().contains("conditional-capability-activation-unresolved:security"));
        assertTrue(analysis.unknowns().contains(
                "custom-authentication-provider-behavior-requires-runtime-contract"));

        for (String capability : List.of(
                "persistence-jpa", "persistence", "transactions", "messaging-kafka",
                "messaging-rabbit", "messaging-jms", "messaging", "cache",
                "spring-mvc", "spring-mvc-xml", "servlet-initializer", "web")) {
            assertEquals(OBSERVED, facts.get(capability).state(), capability);
            assertTrue(analysis.activeCapabilities().contains(capability), capability);
        }
        assertEquals(CONDITIONAL, facts.get("scheduler").state());
        assertEquals(CONDITIONAL, facts.get("database-provider-postgresql").state());
        assertFalse(analysis.activeCapabilities().contains("database-provider-postgresql"));
        assertEquals(DECLARED_ONLY, facts.get("persistence-provider-hibernate").state());
        assertTrue(analysis.unknowns().contains(
                "dynamic-spring-registration-requires-runtime-introspection"));

        assertTrue(facts.get("transactions").sourceTraces().stream()
                .anyMatch(trace -> trace.matches("observed\\|source\\|src/main/java/example/Workflows\\.java:3\\|.*")));
        assertTrue(facts.get("scheduler").activationConditions().stream()
                .anyMatch(condition -> condition.startsWith("property-placeholder:")));

        SpringUpgradeModels.Fingerprint enriched = SpringCapabilityFingerprint.enrich(
                new SpringUpgradeModels.Fingerprint(
                        "2.7.18", "17", "maven", List.of(), List.of("spring-boot-parent"),
                        List.of(), Map.of("spring-boot-parent", List.of("pom.xml:spring-boot-starter-parent"))),
                analysis);
        Map<String, Map<String, Object>> contracts = fcmById(enriched);
        assertEquals("conditional", contracts.get("security").get("status"));
        assertTrue(list(contracts.get("security").get("activation_conditions")).stream()
                .anyMatch(condition -> condition.startsWith("profile:")));
        assertTrue(list(contracts.get("transactions").get("obligations"))
                .contains("preserve-propagation-isolation-and-read-only"));
        assertTrue(list(contracts.get("messaging-kafka").get("obligations"))
                .contains("preserve-ack-retry-redelivery-and-dead-letter-policy"));
        assertTrue(list(contracts.get("spring-mvc-xml").get("obligations"))
                .contains("preserve-context-hierarchy-and-load-order"));
    }

    @Test void commentsAndTestSourcesNeverBecomeProductionCapabilities() throws Exception {
        String pom = "<project/>";
        Files.writeString(temporaryDirectory.resolve("pom.xml"), pom);
        write("src/main/java/example/Comments.java", """
                package example;
                // @KafkaListener(topics = "not-active")
                /* @Transactional */
                final class Comments { }
                """);
        write("src/test/java/example/TestConfiguration.java", """
                package example;
                final class TestConfiguration {
                    @Scheduled(cron = "0 * * * * *") void testJob() { }
                    @Cacheable("test") String value() { return "test"; }
                }
                """);

        SpringCapabilityFingerprint.Analysis analysis =
                SpringCapabilityFingerprint.analyze(temporaryDirectory, pom, "pom.xml");
        Map<String, SpringCapabilityFingerprint.CapabilityFact> facts = factsById(analysis);

        assertFalse(facts.containsKey("transactions"));
        assertFalse(facts.containsKey("messaging-kafka"));
        assertEquals(SpringCapabilityFingerprint.EvidenceState.TEST_ONLY, facts.get("scheduler").state());
        assertEquals(SpringCapabilityFingerprint.EvidenceState.TEST_ONLY, facts.get("cache").state());
        assertFalse(analysis.activeCapabilities().contains("scheduler"));
        assertFalse(analysis.activeCapabilities().contains("cache"));
    }

    @Test void traditionalMvcUsesAnExactFrameworkAuthorityInsteadOfPretendingToBeBoot() throws Exception {
        String pom = """
                <project>
                  <properties>
                    <framework.version>${spring.version}</framework.version>
                    <spring.version>5.3.39</spring.version>
                  </properties>
                  <dependencies>
                    <dependency>
                      <groupId>org.springframework</groupId>
                      <artifactId>spring-webmvc</artifactId>
                      <version>${framework.version}</version>
                    </dependency>
                  </dependencies>
                </project>
                """;
        Files.writeString(temporaryDirectory.resolve("pom.xml"), pom);
        write("src/main/java/example/LegacyController.java", """
                package example;
                @Controller
                final class LegacyController {
                    @RequestMapping("/legacy") String legacy() { return "legacy"; }
                }
                """);
        SpringCapabilityFingerprint.Analysis analysis =
                SpringCapabilityFingerprint.analyze(temporaryDirectory, pom, "pom.xml");

        assertEquals("spring-mvc",
                LocalSpringUpgradeExecutionPort.sourceFrameworkFamily("", analysis));
        var document = DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(
                new ByteArrayInputStream(pom.getBytes(StandardCharsets.UTF_8)));
        assertEquals("5.3.39", LocalSpringUpgradeExecutionPort.springFrameworkVersion(document));
        assertEquals("5.3.39", LocalSpringUpgradeExecutionPort.springFrameworkVersion("""
                dependencies {
                  implementation("org.springframework:spring-webmvc:5.3.39")
                }
                """));
        assertEquals("spring-boot",
                LocalSpringUpgradeExecutionPort.sourceFrameworkFamily("2.7.18", analysis));

        SpringUpgradeModels.Fingerprint enriched = SpringCapabilityFingerprint.enrich(
                new SpringUpgradeModels.Fingerprint(
                        "UNKNOWN", "8", "maven", List.of(), List.of(), List.of(), Map.of(),
                        "spring-mvc", "5.3.39"),
                analysis);
        assertEquals("spring-mvc", enriched.sourceFrameworkFamily());
        assertEquals("5.3.39", enriched.sourceFrameworkVersion());
        assertTrue(enriched.activeCapabilities().contains("spring-mvc"));
    }


    @Test void plainSpringFrameworkUsesItsOwnFamilyWhenBeanBehaviorIsObserved() throws Exception {
        String pom = """
                <project>
                  <dependencies>
                    <dependency>
                      <groupId>org.springframework</groupId>
                      <artifactId>spring-context</artifactId>
                      <version>6.2.8</version>
                    </dependency>
                  </dependencies>
                </project>
                """;
        Files.writeString(temporaryDirectory.resolve("pom.xml"), pom);
        write("src/main/java/example/AppConfig.java", """
                package example;
                @Configuration
                class AppConfig {
                    @Bean Object value() { return new Object(); }
                }
                """);

        SpringCapabilityFingerprint.Analysis analysis =
                SpringCapabilityFingerprint.analyze(temporaryDirectory, pom, "pom.xml");

        assertEquals("spring-framework",
                LocalSpringUpgradeExecutionPort.sourceFrameworkFamily("", analysis, true));
        assertTrue(analysis.activeCapabilities().contains("spring-framework"));
    }

    private void write(String relative, String content) throws Exception {
        Path target = temporaryDirectory.resolve(relative);
        Files.createDirectories(target.getParent());
        Files.writeString(target, content);
    }

    private static Map<String, SpringCapabilityFingerprint.CapabilityFact> factsById(
            SpringCapabilityFingerprint.Analysis analysis) {
        return analysis.facts().stream().collect(Collectors.toMap(
                SpringCapabilityFingerprint.CapabilityFact::id, Function.identity()));
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Map<String, Object>> fcmById(SpringUpgradeModels.Fingerprint fingerprint) {
        return SpringCapabilityFingerprint.fcmCapabilities(fingerprint).stream()
                .collect(Collectors.toMap(
                        capability -> (String) capability.get("id"),
                        Function.identity()));
    }

    @SuppressWarnings("unchecked")
    private static List<String> list(Object value) {
        return (List<String>) value;
    }
}
