package io.elmos.worker;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import javax.xml.parsers.DocumentBuilderFactory;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.io.ByteArrayInputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

import static io.elmos.worker.SpringCapabilityFingerprint.EvidenceState.CONDITIONAL;
import static io.elmos.worker.SpringCapabilityFingerprint.EvidenceState.DECLARED_ONLY;
import static io.elmos.worker.SpringCapabilityFingerprint.EvidenceState.OBSERVED;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
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
                import @Scheduled;
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

    @Test void fcmRendersEveryEvidenceStateAndUnknownCapabilitySafely() {
        SpringUpgradeModels.Fingerprint fingerprint = new SpringUpgradeModels.Fingerprint(
                "UNKNOWN", "11", "maven", List.of(), List.of("active-capability"), List.of(),
                Map.of(
                        "observed-capability", List.of("observed|source|A.java:1|observed"),
                        "conditional-capability", List.of("conditional|source|B.java:1|conditional"),
                        "generated-capability", List.of("generated|source|C.java:1|generated"),
                        "test-capability", List.of("test-only|source|D.java:1|test"),
                        "declared-capability", List.of("declared-only|build-model|pom.xml:1|declared"),
                        "active-capability", List.of(),
                        "unknown-capability", List.of()));

        Map<String, Map<String, Object>> rendered = fcmById(fingerprint);

        assertEquals("observed", rendered.get("observed-capability").get("status"));
        assertEquals("conditional", rendered.get("conditional-capability").get("status"));
        assertEquals("generated", rendered.get("generated-capability").get("status"));
        assertEquals("test-only", rendered.get("test-capability").get("status"));
        assertEquals("declared-only", rendered.get("declared-capability").get("status"));
        assertEquals("observed", rendered.get("active-capability").get("status"));
        assertEquals("unknown", rendered.get("unknown-capability").get("status"));
        assertEquals("build-or-framework", rendered.get("unknown-capability").get("domain"));
        assertEquals("insufficient", rendered.get("unknown-capability").get("confidence"));
        assertTrue(list(rendered.get("observed-capability").get("obligations")).size() >= 4);
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

    @Test void recordsLanguageAndComponentFeatureMappingsForBoot411Fcm() throws Exception {
        Files.writeString(temporaryDirectory.resolve("pom.xml"), "<project/>");
        write("src/main/java/example/App.java", """
                package example;
                @SpringBootApplication
                @RestController
                @Transactional
                @GrpcService
                class App {
                    JsonMapperBuilderCustomizer jacksonCustomizer;
                }
                """);
        write("src/main/kotlin/example/Worker.kt", """
                package example
                @Component
                class Worker
                """);
        write("src/main/groovy/example/ViewController.groovy", """
                package example
                @Controller
                class ViewController { }
                """);
        write("src/main/resources/application.yml", """
                spring:
                  config:
                    import: optional:configtree:/run/secrets/
                server:
                  shutdown: graceful
                """);
        write("src/main/resources/web-context.xml", """
                <beans xmlns:context="http://www.springframework.org/schema/context">
                  <context:component-scan base-package="example"/>
                </beans>
                """);

        SpringCapabilityFingerprint.Analysis analysis =
                SpringCapabilityFingerprint.analyze(temporaryDirectory, "<project/>", "pom.xml");
        Set<String> featureIds = analysis.features().stream()
                .map(SpringUpgradeModels.FeatureObservation::id)
                .collect(Collectors.toSet());

        assertTrue(featureIds.containsAll(Set.of(
                "language-java", "language-kotlin", "language-groovy", "language-configuration",
                "core-bean-di", "boot-application-bootstrap", "mvc-annotated-endpoints",
                "transactions", "boot-config-data", "boot-graceful-shutdown",
                "core-component-scan", "boot-grpc", "boot-jackson")), featureIds.toString());
        SpringUpgradeModels.FeatureObservation kotlin = analysis.features().stream()
                .filter(feature -> feature.id().equals("language-kotlin"))
                .findFirst().orElseThrow();
        assertEquals("observed", kotlin.evidenceState());
        assertEquals("kotlin-compiler-and-spring-kotlin-adapter", kotlin.targetStrategy());
        assertTrue(kotlin.obligations().stream()
                .anyMatch(obligation -> obligation.contains("Java 21") || obligation.contains("Kotlin")));

        SpringUpgradeModels.Fingerprint enriched = SpringCapabilityFingerprint.enrich(
                new SpringUpgradeModels.Fingerprint(
                        "3.5.3", "21", "maven", List.of(), List.of(), List.of(), Map.of()),
                analysis);
        Map<String, Object> boot411 = SpringFeatureCatalog.render(
                enriched.features(), "4.1.1", "21").get(0);
        assertEquals("spring-boot-4.1.1", boot411.get("target"));
        assertTrue(list(boot411.get("obligations")).contains(
                "bind-to-exact-spring-boot-4.1.1-java-21-profile"));

        Map<String, Object> boot353 = SpringFeatureCatalog.render(
                enriched.features(), "3.5.3", "21").get(0);
        assertEquals("spring-boot-3.5.3", boot353.get("target"));
        assertTrue(list(boot353.get("obligations")).contains(
                "bind-to-exact-spring-boot-3.5.3-java-21-profile"));
        assertFalse(list(boot353.get("obligations")).stream()
                .anyMatch(value -> value.contains("4.1.1")));
        assertTrue(enriched.features().stream()
                .anyMatch(feature -> feature.id().equals("boot-config-data")
                        && feature.targetStrategy().contains("config-data")));
    }

    @Test void unmappedSpringConstructsRemainExplicitlyBlocked() throws Exception {
        Files.writeString(temporaryDirectory.resolve("pom.xml"), "<project/>");
        write("src/main/java/example/UnknownSpringFeature.java", """
                package example;
                import org.springframework.unknown.NewContract;
                final class UnknownSpringFeature { NewContract contract; }
                """);

        SpringCapabilityFingerprint.Analysis analysis =
                SpringCapabilityFingerprint.analyze(temporaryDirectory, "<project/>", "pom.xml");

        SpringUpgradeModels.FeatureObservation unknown = analysis.features().stream()
                .filter(feature -> feature.id().equals("unmapped-spring-construct"))
                .findFirst().orElseThrow();
        assertEquals("unknown", unknown.evidenceState());
        assertEquals("unsupported-preserve-and-report", unknown.targetStrategy());
        assertTrue(unknown.obligations().stream()
                .anyMatch(obligation -> obligation.contains("human-or-provider-specific")));
    }

    @Test void defensiveDiscoveryAndFallbackFcmPathsRemainExplicit() throws Exception {
        write("src/main/java/example/LegacySecurity.java", """
                package example;
                class LegacySecurity {
                    WebSecurityConfigurerAdapter adapter;
                    AbstractRoutingDataSource dataSource;
                    ChainedTransactionManager transactionManager;
                    AuthenticationProvider authenticationProvider;
                }
                """);
        write("src/main/generated/example/GeneratedJob.java", """
                package example;
                class GeneratedJob { @Scheduled(cron = "0 * * * * *") void run() { } }
                """);
        write("generated-sources/example/GeneratedSource.java",
                "class GeneratedSource { @Scheduled void run() { } }\n");
        write("project/src/test/java/example/NestedTest.java",
                "class NestedTest { @Scheduled void run() { } }\n");
        write("project/src/main/java/example/NestedMain.java",
                "@Configuration class NestedMain { @Bean Object bean() { return null; } }\n");
        write("Unclassified.java", """
                class Unclassified { @Scheduled(cron = "0 * * * * *") void run() { } }
                """);
        write("target/Excluded.java", "class Excluded { @Scheduled void ignored() { } }");
        write("src/main/java/example/Conditional.java", """
                package example;
                @ConditionalOnProperty(name = "feature", havingValue = "${feature.enabled:false}")
                @Conditional
                class Conditional { }
                """);
        write("src/main/resources/application-prod.yml",
                "# masked comment\nspring:\n  datasource:\n    url: jdbc:h2:mem:test");
        write("src/main/resources/application.yml", "! masked comment\nspring:\n  task:\n    scheduling:\n      pool:\n        size: 2\n");
        write("src/main/resources/settings.properties", "! properties comment\nspring.task.scheduling.pool.size=2\n");
        write("src/main/resources/settings.yaml", "");
        write("src/main/resources/context.xml",
                "<!-- @Transactional\n     @Scheduled -->\n<beans profile=\"prod\"></beans>\n");
        write("src/main/resources/crlf.xml", "<!-- @Transactional\r\n     @Scheduled -->\r\n<beans></beans>\r\n");
        write("src/main/java/example/Huge.java",
                "x".repeat(2 * 1024 * 1024 + 1));

        SpringCapabilityFingerprint.Analysis analysis =
                SpringCapabilityFingerprint.analyze(temporaryDirectory, null, null);
        assertTrue(analysis.unknowns().contains(
                "legacy-security-adapter-requires-rewrite-and-contract-review"));
        assertTrue(analysis.unknowns().contains(
                "dynamic-datasource-routing-requires-runtime-introspection"));
        assertTrue(analysis.unknowns().contains(
                "multi-resource-transaction-semantics-require-provider-contract"));

        Path unknownRoot = temporaryDirectory.resolve("unknown-root");
        Files.createDirectories(unknownRoot);
        Files.writeString(unknownRoot.resolve("Unclassified.java"),
                "class Unclassified { @Scheduled void run() { } }\n");
        SpringCapabilityFingerprint.Analysis unknownAnalysis =
                SpringCapabilityFingerprint.analyze(unknownRoot, null, null);
        assertTrue(unknownAnalysis.unknowns().contains("capability-semantics-unknown:scheduler"));

        Path generatedRoot = temporaryDirectory.resolve("generated-root");
        Files.createDirectories(generatedRoot.resolve("generated-sources/example"));
        Files.writeString(generatedRoot.resolve("generated-sources/example/Generated.java"),
                "class Generated { @Scheduled void run() { } }\n");
        SpringCapabilityFingerprint.Analysis generatedAnalysis =
                SpringCapabilityFingerprint.analyze(generatedRoot, null, null);
        assertTrue(generatedAnalysis.unknowns().contains(
                "generated-capability-build-activation-unresolved:scheduler"));

        Path emptyRoot = temporaryDirectory.resolve("empty-root");
        Files.createDirectories(emptyRoot);
        SpringCapabilityFingerprint.analyze(emptyRoot, "", "");
        SpringCapabilityFingerprint.analyze(temporaryDirectory, null, "   ");

        SpringUpgradeModels.Fingerprint fallback = new SpringUpgradeModels.Fingerprint(
                "UNKNOWN", "21", "maven", List.of(), List.of(), List.of(), Map.of(
                        "validation", List.of("observed|source|Validation.java:1|validation"),
                        "actuator", List.of("observed|source|Actuator.java:1|actuator"),
                        "persistence", List.of("unknown|source|Persistence.java:1|persistence|conditions= ,value"),
                        "messaging", List.of("unknown|source|Messaging.java:1|messaging"),
                        "web", List.of("unknown|source|Web.java:1|web"),
                        "security", List.of("unknown|source|Security.java:1|security")));
        Map<String, Map<String, Object>> contracts = fcmById(fallback);
        assertEquals("validation", contracts.get("validation").get("domain"));
        assertEquals("operations", contracts.get("actuator").get("domain"));
        assertEquals("persistence", contracts.get("persistence").get("domain"));
        assertEquals("unknown", contracts.get("persistence").get("status"));
        assertTrue(list(contracts.get("persistence").get("obligations"))
                .contains("preserve-cross-capability-ordering"));

        new SpringCapabilityFingerprint.Analysis(List.of(), List.of(), Map.of(), List.of());
        new SpringCapabilityFingerprint.Analysis(List.of(), List.of(), Map.of(), List.of(), null);

        InvocationTargetException oddSourcePatterns = assertThrows(InvocationTargetException.class,
                () -> invokePrivate("sources", new Class<?>[]{String[].class},
                        (Object) new String[]{"only-an-expression"}));
        assertTrue(oddSourcePatterns.getCause() instanceof IllegalArgumentException);
        assertNull(invokePrivate("boundedRead", new Class<?>[]{Path.class}, temporaryDirectory));
        assertNull(invokePrivate("boundedRead", new Class<?>[]{Path.class},
                temporaryDirectory.resolve("src/main/java/example/Huge.java")));
        InvocationTargetException missingRoot = assertThrows(InvocationTargetException.class,
                () -> invokePrivate("sourceFiles", new Class<?>[]{Path.class},
                        temporaryDirectory.resolve("does-not-exist")));
        assertTrue(missingRoot.getCause() instanceof IllegalStateException);
        invokePrivate("derive", new Class<?>[]{Map.class, String.class, List.class},
                new java.util.HashMap<>(), "aggregate", List.of("missing-child"));
        assertTrue((Boolean) invokePrivate("ignoredCodeLine",
                new Class<?>[]{Path.class, String.class, int.class},
                Path.of("Example.java"), "import org.springframework.Context;", 0));
        assertTrue((Boolean) invokePrivate("ignoredCodeLine",
                new Class<?>[]{Path.class, String.class, int.class},
                Path.of("Example.java"), "package example;", 0));
        assertTrue((Boolean) invokePrivate("ignoredCodeLine",
                new Class<?>[]{Path.class, String.class, int.class},
                Path.of("Example.java"), "static import example.Context;", 0));
        assertFalse((Boolean) invokePrivate("ignoredCodeLine",
                new Class<?>[]{Path.class, String.class, int.class},
                Path.of("Example.java"), "class Example {}", 0));
        Path incompatibleRoot = (Path) Proxy.newProxyInstance(
                Path.class.getClassLoader(), new Class<?>[]{Path.class}, (proxy, method, arguments) -> {
                    if (method.getName().equals("toAbsolutePath") || method.getName().equals("normalize")) {
                        return proxy;
                    }
                    if (method.getName().equals("relativize")) {
                        throw new IllegalArgumentException("different filesystem providers");
                    }
                    throw new UnsupportedOperationException(method.getName());
                });
        assertTrue((Boolean) invokePrivate("containsExcludedSegment",
                new Class<?>[]{Path.class, Path.class}, incompatibleRoot, Path.of("/tmp/file.java")));
        assertEquals("", invokePrivate("compact", new Class<?>[]{String.class}, (Object) null));
        assertEquals(240, ((String) invokePrivate("compact", new Class<?>[]{String.class},
                "x".repeat(241))).length());
    }

    @Test void classifiesNonStandardAndLegacyComponents() throws Exception {
        String buildGradle = """
                plugins {
                    id 'java'
                }
                dependencies {
                    compile 'javax.validation:validation-api:2.0.1.Final'
                    compile 'com.example:spring-boot-starter-custom:1.0.0'
                }
                """;
        Files.writeString(temporaryDirectory.resolve("build.gradle"), buildGradle);
        write("src/main/java/example/LegacyController.java", """
                package example;
                import javax.validation.constraints.NotNull;
                import org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter;
                public class LegacyController extends WebSecurityConfigurerAdapter {
                    @NotNull private String name;
                }
                """);

        SpringCapabilityFingerprint.Analysis analysis =
                SpringCapabilityFingerprint.analyze(temporaryDirectory, buildGradle, "build.gradle");

        assertTrue(analysis.unknowns().contains("legacy-javax-validation-requires-jakarta-migration"));
        assertTrue(analysis.unknowns().contains("deprecated-websecurity-adapter-requires-security-filter-chain"));
        assertTrue(analysis.unknowns().contains("legacy-gradle-configurations-require-modernization"));
        assertTrue(analysis.unknowns().contains("custom-spring-boot-starter-requires-compatibility-verification"));

        Map<String, SpringCapabilityFingerprint.CapabilityFact> facts = factsById(analysis);
        assertEquals(OBSERVED, facts.get("legacy-javax-validation").state());
        assertEquals(OBSERVED, facts.get("deprecated-websecurity-adapter").state());
        assertEquals(DECLARED_ONLY, facts.get("legacy-gradle-configurations").state());
        assertEquals(DECLARED_ONLY, facts.get("custom-spring-boot-starter").state());
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

    private static Object invokePrivate(String name, Class<?>[] parameterTypes, Object... arguments)
            throws Exception {
        Method method = SpringCapabilityFingerprint.class.getDeclaredMethod(name, parameterTypes);
        method.setAccessible(true);
        return method.invoke(null, arguments);
    }
}
