package io.elmos.worker;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import static io.elmos.worker.SpringUpgradeModels.Fingerprint;

/**
 * Conservative static discovery for Spring behavior that has materially
 * different migration contracts across framework and provider versions.
 *
 * <p>A build dependency is evidence that a capability is available, not that
 * the application activates it. Only an unconditional production source or
 * configuration use is included in {@link Analysis#activeCapabilities()}.
 * Conditional, generated, test-only, declared-only and unknown evidence is
 * retained in source traces and the FCM instead of being flattened into an
 * active claim.</p>
 */
final class SpringCapabilityFingerprint {
    private static final long MAX_DISCOVERY_FILE_BYTES = 2L * 1024 * 1024;
    private static final int MAX_TRACES_PER_CAPABILITY = 100;
    private static final Set<String> EXCLUDED_DIRECTORIES = Set.of(
            ".git", "target", "build", ".gradle", ".idea", ".vscode", ".elmos", "node_modules");
    private static final Set<String> SOURCE_SUFFIXES = Set.of(
            ".java", ".kt", ".groovy", ".xml", ".properties", ".yml", ".yaml");
    private static final Pattern NON_STANDARD_STARTER_GRADLE = Pattern.compile(
            "['\"](?!org\\.springframework\\.boot:)[^'\"]+:(?:spring-boot-starter-[a-zA-Z0-9_-]+|[a-zA-Z0-9_-]+-spring-boot-starter)(?::|['\"])");
    private static final Pattern NON_STANDARD_STARTER_MAVEN = Pattern.compile(
            "<dependency>\\s*<groupId>(?!org\\.springframework\\.boot<)[^<]+</groupId>\\s*<artifactId>(?:spring-boot-starter-[a-zA-Z0-9_-]+|[a-zA-Z0-9_-]+-spring-boot-starter)</artifactId>",
            Pattern.DOTALL);

    enum EvidenceState {
        OBSERVED("observed"),
        CONDITIONAL("conditional"),
        GENERATED("generated"),
        TEST_ONLY("test-only"),
        DECLARED_ONLY("declared-only"),
        UNKNOWN("unknown");

        private final String wireValue;

        EvidenceState(String wireValue) {
            this.wireValue = wireValue;
        }

        String wireValue() {
            return wireValue;
        }
    }

    record CapabilityFact(
            String id,
            String domain,
            EvidenceState state,
            List<String> sourceTraces,
            List<String> activationConditions,
            List<String> obligations
    ) {
        CapabilityFact {
            sourceTraces = List.copyOf(sourceTraces);
            activationConditions = List.copyOf(activationConditions);
            obligations = List.copyOf(obligations);
        }
    }

    record Analysis(
            List<String> activeCapabilities,
            List<String> unknowns,
            Map<String, List<String>> sourceTraces,
            List<CapabilityFact> facts,
            List<SpringUpgradeModels.FeatureObservation> features
    ) {
        Analysis {
            activeCapabilities = List.copyOf(activeCapabilities);
            unknowns = List.copyOf(unknowns);
            sourceTraces = Map.copyOf(sourceTraces);
            facts = List.copyOf(facts);
            features = features == null ? List.of() : List.copyOf(features);
        }

        Analysis(
                List<String> activeCapabilities,
                List<String> unknowns,
                Map<String, List<String>> sourceTraces,
                List<CapabilityFact> facts
        ) {
            this(activeCapabilities, unknowns, sourceTraces, facts, List.of());
        }
    }

    private record SourcePattern(Pattern expression, String label) {
        static SourcePattern of(String expression, String label) {
            return new SourcePattern(Pattern.compile(expression, Pattern.MULTILINE), label);
        }
    }

    private record Rule(
            String id,
            String domain,
            List<String> buildMarkers,
            List<SourcePattern> sourcePatterns,
            List<String> obligations
    ) {}

    private static final class MutableFact {
        private final Rule rule;
        private final Map<EvidenceState, Set<String>> traces = new LinkedHashMap<>();
        private final Set<String> conditions = new TreeSet<>();

        private MutableFact(Rule rule) {
            this.rule = rule;
        }

        void add(EvidenceState state, String trace, List<String> foundConditions) {
            traces.computeIfAbsent(state, ignored -> new TreeSet<>()).add(trace);
            conditions.addAll(foundConditions);
        }

        boolean hasEvidence() {
            return !traces.isEmpty();
        }

        EvidenceState state() {
            if (traces.containsKey(EvidenceState.OBSERVED)) return EvidenceState.OBSERVED;
            if (traces.containsKey(EvidenceState.CONDITIONAL)) return EvidenceState.CONDITIONAL;
            if (traces.containsKey(EvidenceState.GENERATED)) return EvidenceState.GENERATED;
            if (traces.containsKey(EvidenceState.TEST_ONLY)) return EvidenceState.TEST_ONLY;
            if (traces.containsKey(EvidenceState.DECLARED_ONLY)) return EvidenceState.DECLARED_ONLY;
            return EvidenceState.UNKNOWN;
        }

        CapabilityFact immutable() {
            return new CapabilityFact(
                    rule.id(),
                    rule.domain(),
                    state(),
                    traces.values().stream()
                            .flatMap(Set::stream)
                            .distinct()
                            .sorted()
                            .limit(MAX_TRACES_PER_CAPABILITY)
                            .toList(),
                    conditions.stream().toList(),
                    rule.obligations());
        }
    }

    private static final List<String> BASE_OBLIGATIONS = List.of(
            "target-build",
            "target-startup",
            "source-target-behavior-comparison",
            "conditional-activation-reconciliation");

    private static final List<Rule> RULES = List.of(
            rule("security", "security",
                    builds("spring-boot-starter-security", "spring-security-config", "spring-security-web"),
                    sources(
                            "@(?:EnableWebSecurity|EnableGlobalMethodSecurity|EnableMethodSecurity)\\b", "security enablement",
                            "\\bSecurityFilterChain\\b", "security filter chain",
                            "\\bWebSecurityConfigurerAdapter\\b", "legacy security adapter",
                            "\\bHttpSecurity\\b", "HTTP security configuration",
                            "springSecurityFilterChain|DelegatingFilterProxy", "servlet security filter",
                            "<(?:(?:security):)?http\\b", "XML security chain"),
                    "preserve-filter-chain-order", "preserve-session-and-security-context-policy",
                    "preserve-csrf-cors-and-request-cache-defaults", "deny-unmatched-and-error-paths-by-default"),
            rule("authentication", "security",
                    builds(),
                    sources(
                            "\\bAuthenticationProvider\\b", "authentication provider",
                            "\\bUserDetailsService\\b", "user details service",
                            "\\bAuthenticationManager\\b", "authentication manager",
                            "\\bPasswordEncoder\\b", "password encoder",
                            "\\bDaoAuthenticationProvider\\b", "DAO authentication provider",
                            "\\.(?:formLogin|httpBasic|oauth2Login|oauth2ResourceServer|x509)\\s*\\(", "authentication mechanism"),
                    "preserve-credential-extraction", "preserve-provider-order-and-fallback",
                    "preserve-password-and-token-validation", "preserve-authentication-failure-contract"),
            rule("authorization", "security",
                    builds(),
                    sources(
                            "@(?:PreAuthorize|PostAuthorize|PreFilter|PostFilter|Secured|RolesAllowed)\\b", "method authorization",
                            "\\.(?:authorizeHttpRequests|authorizeRequests)\\s*\\(", "request authorization",
                            "\\.(?:requestMatchers|antMatchers|mvcMatchers)\\s*\\(", "authorization matcher",
                            "\\b(?:hasRole|hasAuthority|hasAnyRole|hasAnyAuthority|access)\\s*\\(", "authorization decision",
                            "\\bAccessDecisionManager\\b", "access decision manager"),
                    "preserve-matcher-and-rule-order", "preserve-role-prefix-and-authority-mapping",
                    "preserve-method-security-proxy-boundaries", "preserve-access-denied-status-and-handler"),
            rule("persistence-jpa", "persistence",
                    builds("spring-boot-starter-data-jpa", "spring-data-jpa", "jakarta.persistence-api", "javax.persistence-api"),
                    sources(
                            "@(?:Entity|MappedSuperclass|Embeddable|Converter)\\b", "JPA mapping",
                            "\\b(?:JpaRepository|EntityManager|EntityManagerFactory)\\b", "JPA runtime API",
                            "@EnableJpaRepositories\\b", "JPA repository enablement",
                            "LocalContainerEntityManagerFactoryBean|persistence-unit|<persistence\\b", "JPA persistence unit"),
                    "preserve-entity-and-column-mapping", "preserve-fetch-cascade-and-orphan-semantics",
                    "preserve-flush-lock-and-exception-timing", "preserve-identifier-and-schema-generation"),
            rule("persistence-jdbc", "persistence",
                    builds("spring-boot-starter-jdbc", "spring-jdbc", "spring-data-jdbc"),
                    sources(
                            "\\b(?:JdbcTemplate|NamedParameterJdbcTemplate|SimpleJdbcCall|RowMapper)\\b", "Spring JDBC API",
                            "@EnableJdbcRepositories\\b", "JDBC repository enablement",
                            "\\bDataSource\\b", "data source configuration",
                            "\\bAbstractRoutingDataSource\\b", "AbstractRoutingDataSource dynamic routing",
                            "spring\\.datasource\\.", "data source properties"),
                    "preserve-sql-and-parameter-binding", "preserve-result-and-null-mapping",
                    "preserve-connection-pool-and-timeout-policy", "preserve-sql-exception-translation"),
            rule("persistence-provider-hibernate", "persistence",
                    builds("hibernate-core", "hibernate-entitymanager"),
                    sources(
                            "org\\.hibernate\\.|HibernateJpaVendorAdapter", "Hibernate provider API",
                            "hibernate\\.(?:dialect|ddl-auto)|spring\\.jpa\\.database-platform.*Hibernate", "Hibernate provider configuration",
                            "<provider>\\s*org\\.hibernate\\.", "Hibernate persistence provider"),
                    "pin-provider-and-dialect-version", "preserve-dirty-checking-and-flush-mode",
                    "preserve-proxy-lazy-loading-semantics", "verify-generated-ddl-and-query-behavior"),
            rule("persistence-provider-eclipselink", "persistence",
                    builds("org.eclipse.persistence", "eclipselink"),
                    sources(
                            "org\\.eclipse\\.persistence\\.|EclipseLinkJpaVendorAdapter", "EclipseLink provider API",
                            "eclipselink\\.|<provider>\\s*org\\.eclipse\\.persistence", "EclipseLink provider configuration"),
                    "pin-provider-and-dialect-version", "preserve-weaving-and-change-tracking",
                    "preserve-fetch-and-cache-semantics", "verify-generated-ddl-and-query-behavior"),
            rule("persistence-provider-openjpa", "persistence",
                    builds("openjpa"),
                    sources(
                            "org\\.apache\\.openjpa\\.|OpenJpaVendorAdapter", "OpenJPA provider API",
                            "openjpa\\.|<provider>\\s*org\\.apache\\.openjpa", "OpenJPA provider configuration"),
                    "pin-provider-and-dialect-version", "preserve-enhancement-and-fetch-semantics",
                    "preserve-query-and-locking-semantics", "verify-generated-ddl-and-query-behavior"),
            databaseProvider("postgresql", "postgresql", "jdbc:postgresql:"),
            databaseProvider("mysql", "mysql-connector", "jdbc:mysql:"),
            databaseProvider("mariadb", "mariadb-java-client", "jdbc:mariadb:"),
            databaseProvider("oracle", "ojdbc", "jdbc:oracle:"),
            databaseProvider("sqlserver", "mssql-jdbc", "jdbc:sqlserver:"),
            databaseProvider("h2", "h2", "jdbc:h2:"),
            rule("transactions", "transaction",
                    builds("spring-tx", "spring-boot-starter-jta", "atomikos", "narayana"),
                    sources(
                            "@Transactional\\b", "transaction boundary",
                            "@EnableTransactionManagement\\b", "transaction management enablement",
                            "\\b(?:PlatformTransactionManager|TransactionTemplate|TransactionOperations)\\b", "transaction manager API",
                            "<tx:(?:annotation-driven|advice)\\b", "XML transaction configuration",
                            "\\b(?:JtaTransactionManager|ChainedTransactionManager)\\b", "multi-resource transaction manager"),
                    "preserve-propagation-isolation-and-read-only", "preserve-timeout-and-rollback-rules",
                    "preserve-manager-qualification-and-resource-binding", "preserve-commit-rollback-and-exception-timing",
                    "verify-proxy-and-self-invocation-boundaries"),
            messagingRule("messaging-kafka", "spring-kafka", "kafka-clients",
                    "@KafkaListener\\b", "Kafka listener",
                    "\\bKafkaTemplate\\b", "Kafka producer",
                    "@EnableKafka\\b|KafkaListenerContainerFactory", "Kafka listener infrastructure",
                    "spring\\.kafka\\.", "Kafka configuration"),
            messagingRule("messaging-rabbit", "spring-rabbit", "spring-boot-starter-amqp",
                    "@RabbitListener\\b", "Rabbit listener",
                    "\\bRabbitTemplate\\b", "Rabbit producer",
                    "@EnableRabbit\\b|RabbitListenerContainerFactory", "Rabbit listener infrastructure",
                    "spring\\.rabbitmq\\.", "Rabbit configuration"),
            messagingRule("messaging-jms", "spring-jms", "spring-boot-starter-artemis",
                    "@JmsListener\\b", "JMS listener",
                    "\\bJmsTemplate\\b", "JMS producer",
                    "@EnableJms\\b|JmsListenerContainerFactory", "JMS listener infrastructure",
                    "spring\\.jms\\.|spring\\.artemis\\.|spring\\.activemq\\.", "JMS configuration"),
            rule("cache", "cache",
                    builds("spring-boot-starter-cache", "spring-context-support", "caffeine", "ehcache", "hazelcast"),
                    sources(
                            "@(?:Cacheable|CachePut|CacheEvict|Caching)\\b", "cache operation",
                            "@EnableCaching\\b", "cache enablement",
                            "\\bCacheManager\\b", "cache manager",
                            "<cache:annotation-driven\\b", "XML cache configuration",
                            "spring\\.cache\\.", "cache properties"),
                    "preserve-cache-name-key-and-key-generator", "preserve-condition-unless-and-null-policy",
                    "preserve-ttl-serialization-and-provider-semantics", "preserve-sync-and-eviction-order"),
            rule("scheduler", "scheduler",
                    builds("quartz", "spring-boot-starter-quartz"),
                    sources(
                            "@Scheduled\\b", "scheduled method",
                            "@EnableScheduling\\b", "scheduler enablement",
                            "\\b(?:TaskScheduler|SchedulingConfigurer|ScheduledTaskRegistrar)\\b", "scheduler infrastructure",
                            "\\b(?:CronTrigger|QuartzJobBean|SchedulerFactoryBean)\\b", "Quartz scheduling",
                            "spring\\.(?:task\\.scheduling|quartz)\\.", "scheduler properties"),
                    "preserve-cron-fixed-rate-delay-and-time-zone", "preserve-concurrency-and-overlap-policy",
                    "preserve-misfire-startup-and-shutdown-semantics", "preserve-transaction-and-security-context"),
            rule("spring-framework", "framework",
                    builds("spring-core", "spring-context", "spring-beans", "spring-expression", "spring-aop"),
                    sources(
                            "@(?:Configuration|Component|Service|Repository|Bean)\\b", "Spring bean declaration",
                            "\\b(?:ApplicationContext|AnnotationConfigApplicationContext|BeanFactory)\\b", "Spring context API",
                            "\\b(?:Import|ComponentScan|Profile|Qualifier|Primary)\\b", "Spring configuration contract"),
                    "preserve-bean-graph-and-context-ownership", "preserve-component-scan-and-profile-conditions",
                    "preserve-bean-lifecycle-and-proxy-boundaries", "require-source-runtime-entry-point"),
            rule("spring-mvc", "web",
                    builds("spring-webmvc", "spring-boot-starter-web"),
                    sources(
                            "@(?:Controller|RestController|ControllerAdvice|RestControllerAdvice)\\b", "Spring MVC controller",
                            "@(?:RequestMapping|GetMapping|PostMapping|PutMapping|PatchMapping|DeleteMapping)\\b", "Spring MVC route",
                            "\\b(?:HandlerInterceptor|HandlerExceptionResolver|WebMvcConfigurer)\\b", "Spring MVC extension",
                            "<mvc:(?:annotation-driven|resources|interceptors|view-controller)\\b", "Spring MVC XML namespace",
                            "org\\.springframework\\.web\\.servlet\\.view\\.", "Spring MVC view resolver"),
                    "preserve-route-method-media-and-parameter-contract", "preserve-binding-validation-and-error-contract",
                    "preserve-interceptor-exception-and-view-resolution-order", "preserve-session-async-and-multipart-semantics"),
            rule("spring-mvc-xml", "web",
                    builds(),
                    sources(
                            "<mvc:(?:annotation-driven|resources|interceptors|view-controller)\\b", "Spring MVC XML namespace",
                            "<context:component-scan\\b", "XML component scan",
                            "org\\.springframework\\.web\\.servlet\\.(?:DispatcherServlet|view\\.)", "XML MVC component",
                            "<bean[^>]+(?:HandlerMapping|HandlerAdapter|ViewResolver|HandlerExceptionResolver)", "XML MVC strategy bean"),
                    "preserve-bean-ids-aliases-and-reference-integrity", "preserve-context-hierarchy-and-load-order",
                    "preserve-namespace-handler-defaults", "preserve-component-scan-includes-and-excludes"),
            rule("servlet-initializer", "web",
                    builds(),
                    sources(
                            "\\bWebApplicationInitializer\\b", "Servlet 3 application initializer",
                            "AbstractAnnotationConfigDispatcherServletInitializer", "annotation MVC initializer",
                            "\\bDispatcherServlet\\b", "dispatcher servlet registration",
                            "org\\.springframework\\.web\\.servlet\\.DispatcherServlet|<servlet-name>[^<]*dispatcher", "web.xml dispatcher servlet"),
                    "preserve-root-and-servlet-context-hierarchy", "preserve-servlet-mapping-and-load-on-startup",
                    "preserve-filter-listener-and-initializer-order", "preserve-async-and-multipart-registration"),
            rule("validation", "validation",
                    builds("spring-boot-starter-validation", "hibernate-validator", "jakarta.validation-api", "validation-api"),
                    sources(
                            "@(?:Valid|Validated)\\b", "validation boundary",
                            "\\bConstraintValidator\\b|@Constraint\\b", "custom validation constraint",
                            "\\bValidatorFactory\\b|LocalValidatorFactoryBean", "validation provider configuration"),
                    "preserve-validation-groups-and-order", "preserve-cascade-and-container-element-validation",
                    "preserve-message-interpolation-and-locale", "preserve-binding-error-shape-and-timing"),
            rule("actuator", "operations",
                    builds("spring-boot-starter-actuator"),
                    sources(
                            "management\\.endpoints?\\.", "actuator endpoint configuration",
                            "@(?:Endpoint|ReadOperation|WriteOperation|DeleteOperation)\\b", "custom actuator endpoint"),
                    "preserve-endpoint-exposure-and-base-path", "preserve-health-readiness-and-liveness-semantics",
                    "preserve-management-port-and-security-policy", "preserve-sensitive-value-redaction"),
            rule("dynamic-spring-registration", "lifecycle",
                    builds(),
                    sources(
                            "\\b(?:ImportBeanDefinitionRegistrar|ImportSelector|DeferredImportSelector)\\b", "dynamic import registration",
                            "\\b(?:BeanDefinitionRegistryPostProcessor|BeanFactoryPostProcessor)\\b", "bean factory mutation",
                            "\\bApplicationContextInitializer\\b", "application context initializer",
                            "\\bClassPathBeanDefinitionScanner\\b", "programmatic component scanning"),
                    "capture-runtime-bean-graph", "preserve-registration-and-post-processor-order",
                    "preserve-environment-and-classpath-conditions", "require-safe-runtime-introspection"),
            rule("legacy-javax-validation", "validation",
                    builds("javax.validation", "validation-api"),
                    sources(
                            "javax\\.validation\\.", "legacy javax.validation import",
                            "@(NotNull|NotEmpty|NotBlank|Size|Min|Max|Pattern|Valid)\\b", "legacy validation constraint"),
                    "migrate-javax-to-jakarta-validation", "verify-validation-message-and-payload"),
            rule("deprecated-websecurity-adapter", "security",
                    builds(),
                    sources(
                            "\\bWebSecurityConfigurerAdapter\\b", "deprecated WebSecurityConfigurerAdapter"),
                    "migrate-adapter-to-security-filter-chain", "verify-security-matcher-and-filter-order"),
            rule("legacy-gradle-configurations", "build",
                    builds("compile", "testCompile"),
                    sources(
                            "(?:^|\\s)(?:compile|testCompile)\\s*[\"'(]", "deprecated Gradle configuration"),
                    "migrate-compile-to-implementation", "verify-dependency-classpath-visibility"),
            rule("custom-spring-boot-starter", "integration",
                    builds(),
                    sources(
                            "(?<!org\\.springframework\\.boot:)spring-boot-starter-[a-zA-Z0-9_-]+", "third-party or custom Spring Boot starter"),
                    "verify-starter-boot3-compatibility", "check-jakarta-namespace-compatibility"));

    private SpringCapabilityFingerprint() {}

    static Analysis analyze(Path root, String buildModel, String buildModelName) {
        Objects.requireNonNull(root, "root");
        String safeBuildModel = buildModel == null ? "" : buildModel;
        String safeBuildName = buildModelName == null || buildModelName.isBlank()
                ? "build-model" : buildModelName;
        Map<String, MutableFact> facts = new TreeMap<>();
        List<SpringUpgradeModels.FeatureObservation> features = new ArrayList<>();
        for (Rule rule : RULES) facts.put(rule.id(), new MutableFact(rule));

        for (Rule rule : RULES) {
            for (String marker : rule.buildMarkers()) {
                int offset = safeBuildModel.indexOf(marker);
                if (offset >= 0) {
                    int line = lineNumber(safeBuildModel, offset);
                    facts.get(rule.id()).add(
                            EvidenceState.DECLARED_ONLY,
                            trace(EvidenceState.DECLARED_ONLY, "build-model", safeBuildName, line,
                                    marker, List.of()),
                            List.of());
                }
            }
        }

        Matcher starterGradle = NON_STANDARD_STARTER_GRADLE.matcher(safeBuildModel);
        while (starterGradle.find()) {
            int line = lineNumber(safeBuildModel, starterGradle.start());
            facts.get("custom-spring-boot-starter").add(
                    EvidenceState.DECLARED_ONLY,
                    trace(EvidenceState.DECLARED_ONLY, "build-model", safeBuildName, line,
                            starterGradle.group(), List.of()),
                    List.of());
        }
        Matcher starterMaven = NON_STANDARD_STARTER_MAVEN.matcher(safeBuildModel);
        while (starterMaven.find()) {
            int line = lineNumber(safeBuildModel, starterMaven.start());
            facts.get("custom-spring-boot-starter").add(
                    EvidenceState.DECLARED_ONLY,
                    trace(EvidenceState.DECLARED_ONLY, "build-model", safeBuildName, line,
                            starterMaven.group(), List.of()),
                    List.of());
        }

        for (Path file : sourceFiles(root)) {
            String raw = boundedRead(file);
            if (raw == null) continue;
            String content = maskComments(file, raw);
            String relative = normalizedRelative(root, file);
            List<String> fileConditions = conditions(file, relative, content);
            EvidenceState baseState = evidenceState(relative, fileConditions);
            features.addAll(SpringFeatureCatalog.observe(file, relative, content, baseState, fileConditions));
            for (Rule rule : RULES) {
                for (SourcePattern sourcePattern : rule.sourcePatterns()) {
                    Matcher matcher = sourcePattern.expression().matcher(content);
                    while (matcher.find()) {
                        int line = lineNumber(content, matcher.start());
                        if (ignoredCodeLine(file, content, matcher.start())) continue;
                        List<String> evidenceConditions = new ArrayList<>(fileConditions);
                        String matchedLine = lineAt(content, matcher.start());
                        if (matchedLine.contains("${")) {
                            evidenceConditions.addAll(propertyPlaceholderConditions(matchedLine));
                        }
                        EvidenceState state = baseState == EvidenceState.OBSERVED
                                && !evidenceConditions.isEmpty() ? EvidenceState.CONDITIONAL : baseState;
                        facts.get(rule.id()).add(
                                state,
                                trace(state, "source", relative, line, sourcePattern.label(), evidenceConditions),
                                evidenceConditions);
                    }
                }
            }
        }

        derive(facts, "security", List.of("authentication", "authorization"));
        derive(facts, "persistence", List.of(
                "persistence-jpa", "persistence-jdbc", "persistence-provider-hibernate",
                "persistence-provider-eclipselink", "persistence-provider-openjpa",
                "database-provider-postgresql", "database-provider-mysql", "database-provider-mariadb",
                "database-provider-oracle", "database-provider-sqlserver", "database-provider-h2"));
        derive(facts, "messaging", List.of("messaging-kafka", "messaging-rabbit", "messaging-jms"));
        derive(facts, "web", List.of("spring-mvc", "spring-mvc-xml", "servlet-initializer"));

        List<CapabilityFact> immutableFacts = facts.values().stream()
                .filter(MutableFact::hasEvidence)
                .map(MutableFact::immutable)
                .sorted(Comparator.comparing(CapabilityFact::id))
                .toList();
        List<String> active = immutableFacts.stream()
                .filter(fact -> fact.state() == EvidenceState.OBSERVED)
                .map(CapabilityFact::id)
                .distinct()
                .sorted()
                .toList();
        Map<String, List<String>> traces = new TreeMap<>();
        for (CapabilityFact fact : immutableFacts) traces.put(fact.id(), fact.sourceTraces());

        Set<String> unknowns = new TreeSet<>();
        for (CapabilityFact fact : immutableFacts) {
            switch (fact.state()) {
                case CONDITIONAL -> unknowns.add(
                        "conditional-capability-activation-unresolved:" + fact.id());
                case GENERATED -> unknowns.add(
                        "generated-capability-build-activation-unresolved:" + fact.id());
                case DECLARED_ONLY -> unknowns.add(
                        "declared-only-capability-runtime-activation-unobserved:" + fact.id());
                case UNKNOWN -> unknowns.add("capability-semantics-unknown:" + fact.id());
                default -> { }
            }
        }
        if (traces.containsKey("dynamic-spring-registration")) {
            unknowns.add("dynamic-spring-registration-requires-runtime-introspection");
        }
        if (containsTrace(traces, "security", "legacy security adapter")) {
            unknowns.add("legacy-security-adapter-requires-rewrite-and-contract-review");
        }
        if (containsTrace(traces, "authentication", "authentication provider")) {
            unknowns.add("custom-authentication-provider-behavior-requires-runtime-contract");
        }
        if (containsTrace(traces, "persistence-jdbc", "AbstractRoutingDataSource")) {
            unknowns.add("dynamic-datasource-routing-requires-runtime-introspection");
        }
        if (containsTrace(traces, "transactions", "multi-resource transaction manager")) {
            unknowns.add("multi-resource-transaction-semantics-require-provider-contract");
        }
        if (traces.containsKey("legacy-javax-validation")) {
            unknowns.add("legacy-javax-validation-requires-jakarta-migration");
        }
        if (traces.containsKey("deprecated-websecurity-adapter")) {
            unknowns.add("deprecated-websecurity-adapter-requires-security-filter-chain");
        }
        if (traces.containsKey("legacy-gradle-configurations")) {
            unknowns.add("legacy-gradle-configurations-require-modernization");
        }
        if (traces.containsKey("custom-spring-boot-starter")) {
            unknowns.add("custom-spring-boot-starter-requires-compatibility-verification");
        }
        return new Analysis(active, unknowns.stream().toList(), traces, immutableFacts,
                SpringFeatureCatalog.merge(List.of(), features));
    }

    static Fingerprint enrich(Fingerprint base, Analysis analysis) {
        Objects.requireNonNull(base, "base");
        Objects.requireNonNull(analysis, "analysis");
        Set<String> capabilities = new TreeSet<>(base.activeCapabilities());
        capabilities.addAll(analysis.activeCapabilities());
        Set<String> unknowns = new TreeSet<>(base.unknowns());
        unknowns.addAll(analysis.unknowns());
        Map<String, List<String>> traces = new TreeMap<>();
        base.sourceTraces().forEach((id, values) -> traces.put(id, new ArrayList<>(values)));
        analysis.sourceTraces().forEach((id, values) -> {
            List<String> merged = new ArrayList<>(traces.getOrDefault(id, List.of()));
            merged.addAll(values);
            traces.put(id, merged.stream().distinct().sorted().limit(MAX_TRACES_PER_CAPABILITY).toList());
        });
        List<SpringUpgradeModels.FeatureObservation> features = SpringFeatureCatalog.merge(
                base.features(), analysis.features());
        return new Fingerprint(
                base.springBootVersion(),
                base.javaVersion(),
                base.buildTool(),
                base.modules(),
                capabilities.stream().toList(),
                unknowns.stream().toList(),
                traces,
                base.sourceFrameworkFamily(),
                base.sourceFrameworkVersion(),
                features);
    }

    static List<Map<String, Object>> fcmCapabilities(Fingerprint fingerprint) {
        Set<String> ids = new TreeSet<>(fingerprint.sourceTraces().keySet());
        ids.addAll(fingerprint.activeCapabilities());
        List<Map<String, Object>> rendered = new ArrayList<>();
        for (String id : ids) {
            List<String> traces = fingerprint.sourceTraces().getOrDefault(id, List.of());
            EvidenceState state = stateFrom(traces,
                    fingerprint.activeCapabilities().contains(id));
            Map<String, Object> capability = new LinkedHashMap<>();
            capability.put("id", id);
            capability.put("domain", domainFor(id));
            capability.put("status", state.wireValue());
            capability.put("confidence", confidenceFor(state));
            capability.put("runtime_confirmation", false);
            capability.put("source_traces", traces);
            capability.put("activation_conditions", conditionsFrom(traces));
            capability.put("obligations", obligationsFor(id));
            rendered.add(capability);
        }
        return List.copyOf(rendered);
    }

    private static Rule databaseProvider(String id, String buildMarker, String jdbcUrl) {
        return rule("database-provider-" + id, "persistence",
                builds(buildMarker),
                sources(Pattern.quote(jdbcUrl), id + " JDBC provider configuration"),
                "pin-driver-database-and-dialect-version", "preserve-type-precision-null-and-collation",
                "preserve-identifier-sequence-and-generated-column-semantics", "preserve-locking-isolation-and-error-codes");
    }

    private static Rule messagingRule(String id, String... patternPairs) {
        List<String> markers = List.of(patternPairs[0], patternPairs[1]);
        List<String> pairs = new ArrayList<>();
        for (int index = 2; index < patternPairs.length; index++) pairs.add(patternPairs[index]);
        return rule(id, "messaging", markers, sources(pairs.toArray(String[]::new)),
                "preserve-destination-and-routing", "preserve-serialization-headers-and-schema",
                "preserve-ack-retry-redelivery-and-dead-letter-policy", "preserve-ordering-concurrency-and-delivery-semantics",
                "preserve-broker-transaction-boundaries");
    }

    private static Rule rule(String id, String domain, List<String> buildMarkers,
                             List<SourcePattern> sourcePatterns, String... obligations) {
        List<String> allObligations = new ArrayList<>(BASE_OBLIGATIONS);
        allObligations.addAll(List.of(obligations));
        return new Rule(id, domain, List.copyOf(buildMarkers), List.copyOf(sourcePatterns),
                allObligations.stream().distinct().toList());
    }

    private static List<String> builds(String... markers) {
        return List.of(markers);
    }

    private static List<SourcePattern> sources(String... expressionLabelPairs) {
        if (expressionLabelPairs.length % 2 != 0) {
            throw new IllegalArgumentException("source patterns require expression/label pairs");
        }
        List<SourcePattern> patterns = new ArrayList<>();
        for (int index = 0; index < expressionLabelPairs.length; index += 2) {
            patterns.add(SourcePattern.of(expressionLabelPairs[index], expressionLabelPairs[index + 1]));
        }
        return List.copyOf(patterns);
    }

    private static void derive(Map<String, MutableFact> facts, String aggregateId, List<String> children) {
        MutableFact aggregate = facts.computeIfAbsent(aggregateId,
                ignored -> new MutableFact(rule(aggregateId, domainFor(aggregateId), builds(), sources(),
                        "preserve-cross-capability-ordering", "verify-provider-specific-defaults")));
        for (String childId : children) {
            MutableFact child = facts.get(childId);
            if (child == null || !child.hasEvidence()) continue;
            CapabilityFact childFact = child.immutable();
            for (String childTrace : childFact.sourceTraces()) {
                aggregate.add(childFact.state(), childTrace + "|derived-from=" + childId,
                        childFact.activationConditions());
            }
        }
    }

    private static List<Path> sourceFiles(Path root) {
        try (var paths = Files.walk(root)) {
            return paths
                    .filter(path -> Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS))
                    .filter(path -> !containsExcludedSegment(root, path))
                    .filter(path -> !"pom.xml".equals(path.getFileName().toString()))
                    .filter(SpringCapabilityFingerprint::hasSourceSuffix)
                    .sorted()
                    .toList();
        } catch (IOException error) {
            throw new IllegalStateException("Spring capability source discovery failed", error);
        }
    }

    private static boolean containsExcludedSegment(Path root, Path path) {
        Path relative;
        try {
            relative = root.toAbsolutePath().normalize().relativize(path.toAbsolutePath().normalize());
        } catch (IllegalArgumentException error) {
            return true;
        }
        for (Path segment : relative) {
            if (EXCLUDED_DIRECTORIES.contains(segment.toString())) return true;
        }
        return false;
    }

    private static boolean hasSourceSuffix(Path path) {
        String name = path.getFileName().toString().toLowerCase(Locale.ROOT);
        return SOURCE_SUFFIXES.stream().anyMatch(name::endsWith);
    }

    private static String boundedRead(Path file) {
        try {
            long size = Files.size(file);
            if (size > MAX_DISCOVERY_FILE_BYTES) return null;
            return Files.readString(file, StandardCharsets.UTF_8);
        } catch (IOException error) {
            return null;
        }
    }

    private static EvidenceState evidenceState(String relative, List<String> conditions) {
        String normalized = relative.toLowerCase(Locale.ROOT);
        if (normalized.contains("/src/test/") || normalized.startsWith("src/test/")) {
            return EvidenceState.TEST_ONLY;
        }
        if (normalized.contains("generated-sources") || normalized.contains("/generated/")) {
            return EvidenceState.GENERATED;
        }
        if (!conditions.isEmpty()) return EvidenceState.CONDITIONAL;
        if (normalized.contains("/src/main/") || normalized.startsWith("src/main/")) {
            return EvidenceState.OBSERVED;
        }
        return EvidenceState.UNKNOWN;
    }

    private static List<String> conditions(Path file, String relative, String content) {
        Set<String> conditions = new TreeSet<>();
        String name = file.getFileName().toString();
        Matcher profileFile = Pattern.compile("application-([^.]+)\\.(?:properties|ya?ml)$")
                .matcher(name);
        if (profileFile.find()) conditions.add("profile-file:" + profileFile.group(1));
        collectConditions(content, conditions,
                Pattern.compile("@Profile\\s*\\(([^)]{1,200})\\)"), "profile:");
        collectConditions(content, conditions,
                Pattern.compile("@(Conditional(?:On[A-Za-z]+)?)\\s*(?:\\(([^)]{0,300})\\))?"), "condition:");
        collectConditions(content, conditions,
                Pattern.compile("<(?:beans(?::beans)?)\\b[^>]*\\bprofile\\s*=\\s*[\"']([^\"']+)[\"']"),
                "xml-profile:");
        String normalizedRelative = relative.toLowerCase(Locale.ROOT);
        if (normalizedRelative.contains("/src/test/") || normalizedRelative.startsWith("src/test/")) {
            conditions.add("test-scope");
        }
        return conditions.stream().map(SpringCapabilityFingerprint::compact).toList();
    }

    private static void collectConditions(String content, Set<String> target, Pattern pattern, String prefix) {
        Matcher matcher = pattern.matcher(content);
        while (matcher.find()) {
            String value = matcher.groupCount() >= 2 && matcher.group(2) != null
                    ? matcher.group(1) + ":" + matcher.group(2)
                    : matcher.group(1);
            target.add(prefix + compact(value));
        }
    }

    /** Keep placeholder names for activation provenance without retaining defaults or secret values. */
    private static List<String> propertyPlaceholderConditions(String line) {
        Set<String> names = new TreeSet<>();
        Matcher matcher = Pattern.compile("\\$\\{([A-Za-z0-9_.-]+)(?::[^}]*)?}").matcher(line);
        while (matcher.find()) names.add("property-placeholder:" + matcher.group(1));
        return names.stream().toList();
    }

    private static String maskComments(Path file, String content) {
        String name = file.getFileName().toString().toLowerCase(Locale.ROOT);
        if (name.endsWith(".xml")) {
            return maskPattern(content, Pattern.compile("<!--.*?-->", Pattern.DOTALL));
        }
        if (name.endsWith(".properties") || name.endsWith(".yml") || name.endsWith(".yaml")) {
            StringBuilder masked = new StringBuilder(content.length());
            for (String line : content.split("\\n", -1)) {
                String trimmed = line.stripLeading();
                masked.append(trimmed.startsWith("#") || trimmed.startsWith("!")
                        ? " ".repeat(line.length()) : line).append('\n');
            }
            if (!content.endsWith("\n")) masked.setLength(masked.length() - 1);
            return masked.toString();
        }
        String withoutBlocks = maskPattern(content, Pattern.compile("/\\*.*?\\*/", Pattern.DOTALL));
        return maskPattern(withoutBlocks, Pattern.compile("(?m)//[^\\r\\n]*$"));
    }

    private static String maskPattern(String content, Pattern pattern) {
        Matcher matcher = pattern.matcher(content);
        StringBuilder masked = new StringBuilder(content);
        while (matcher.find()) {
            for (int index = matcher.start(); index < matcher.end(); index++) {
                char value = masked.charAt(index);
                if (value != '\n' && value != '\r') masked.setCharAt(index, ' ');
            }
        }
        return masked.toString();
    }

    private static boolean ignoredCodeLine(Path file, String content, int offset) {
        String name = file.getFileName().toString().toLowerCase(Locale.ROOT);
        if (!(name.endsWith(".java") || name.endsWith(".kt") || name.endsWith(".groovy"))) return false;
        String line = lineAt(content, offset).stripLeading();
        return line.startsWith("import ") || line.startsWith("package ") || line.startsWith("static import ");
    }

    private static String trace(EvidenceState state, String kind, String relative, int line,
                                String label, List<String> conditions) {
        StringBuilder trace = new StringBuilder()
                .append(state.wireValue()).append('|')
                .append(compact(kind)).append('|')
                .append(compact(relative)).append(':').append(line).append('|')
                .append(compact(label));
        if (!conditions.isEmpty()) {
            trace.append("|conditions=")
                    .append(conditions.stream().map(SpringCapabilityFingerprint::compact)
                            .distinct().sorted().reduce((left, right) -> left + "," + right).orElse(""));
        }
        return trace.toString();
    }

    private static int lineNumber(String content, int offset) {
        int line = 1;
        for (int index = 0; index < Math.min(offset, content.length()); index++) {
            if (content.charAt(index) == '\n') line++;
        }
        return line;
    }

    private static String lineAt(String content, int offset) {
        int start = content.lastIndexOf('\n', Math.max(0, offset - 1));
        int end = content.indexOf('\n', offset);
        if (end < 0) end = content.length();
        return content.substring(start < 0 ? 0 : start + 1, end);
    }

    private static String normalizedRelative(Path root, Path file) {
        return root.toAbsolutePath().normalize().relativize(file.toAbsolutePath().normalize())
                .toString().replace('\\', '/');
    }

    private static String compact(String value) {
        if (value == null) return "";
        String compacted = value.replaceAll("\\s+", " ").trim()
                .replace('|', '/')
                .replace('\n', ' ')
                .replace('\r', ' ');
        return compacted.length() <= 240 ? compacted : compacted.substring(0, 240);
    }

    private static boolean containsTrace(Map<String, List<String>> traces, String id, String fragment) {
        return traces.getOrDefault(id, List.of()).stream().anyMatch(trace -> trace.contains(fragment));
    }

    private static EvidenceState stateFrom(List<String> traces, boolean active) {
        if (active || hasState(traces, EvidenceState.OBSERVED)) return EvidenceState.OBSERVED;
        if (hasState(traces, EvidenceState.CONDITIONAL)) return EvidenceState.CONDITIONAL;
        if (hasState(traces, EvidenceState.GENERATED)) return EvidenceState.GENERATED;
        if (hasState(traces, EvidenceState.TEST_ONLY)) return EvidenceState.TEST_ONLY;
        if (hasState(traces, EvidenceState.DECLARED_ONLY)) return EvidenceState.DECLARED_ONLY;
        return EvidenceState.UNKNOWN;
    }

    private static boolean hasState(List<String> traces, EvidenceState state) {
        String prefix = state.wireValue() + "|";
        return traces.stream().anyMatch(trace -> trace.startsWith(prefix));
    }

    private static List<String> conditionsFrom(List<String> traces) {
        Set<String> conditions = new TreeSet<>();
        for (String trace : traces) {
            int marker = trace.indexOf("|conditions=");
            if (marker < 0) continue;
            String value = trace.substring(marker + "|conditions=".length());
            for (String condition : value.split(",")) {
                if (!condition.isBlank()) conditions.add(condition);
            }
        }
        return conditions.stream().toList();
    }

    private static String confidenceFor(EvidenceState state) {
        return switch (state) {
            case OBSERVED -> "medium-static-source";
            case CONDITIONAL -> "medium-condition-unresolved";
            case TEST_ONLY -> "high-test-scope-only";
            case GENERATED -> "low-generated-unreconciled";
            case DECLARED_ONLY -> "low-declaration-only";
            case UNKNOWN -> "insufficient";
        };
    }

    private static String domainFor(String id) {
        if (id.equals("authentication") || id.equals("authorization") || id.equals("security")
                || id.equals("deprecated-websecurity-adapter")) return "security";
        if (id.startsWith("persistence") || id.startsWith("database-provider")) return "persistence";
        if (id.equals("transactions")) return "transaction";
        if (id.startsWith("messaging")) return "messaging";
        if (id.equals("cache")) return "cache";
        if (id.equals("scheduler")) return "scheduler";
        if (id.equals("spring-mvc") || id.equals("spring-mvc-xml")
                || id.equals("servlet-initializer") || id.equals("web")) return "web";
        if (id.equals("validation") || id.equals("legacy-javax-validation")) return "validation";
        if (id.equals("actuator")) return "operations";
        if (id.equals("dynamic-spring-registration")) return "lifecycle";
        if (id.equals("legacy-gradle-configurations")) return "build";
        if (id.equals("custom-spring-boot-starter")) return "integration";
        return "build-or-framework";
    }

    private static List<String> obligationsFor(String id) {
        return RULES.stream()
                .filter(rule -> rule.id().equals(id))
                .findFirst()
                .map(Rule::obligations)
                .orElseGet(() -> {
                    List<String> obligations = new ArrayList<>(BASE_OBLIGATIONS);
                    if (Set.of("security", "persistence", "messaging", "web").contains(id)) {
                        obligations.add("preserve-cross-capability-ordering");
                        obligations.add("verify-provider-specific-defaults");
                    }
                    return List.copyOf(obligations);
                });
    }
}
