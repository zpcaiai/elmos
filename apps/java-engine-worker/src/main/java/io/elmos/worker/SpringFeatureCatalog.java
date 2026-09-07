package io.elmos.worker;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import static io.elmos.worker.SpringUpgradeModels.FeatureObservation;

/**
 * Typed inventory of Spring source features which have a distinct target
 * migration contract. The catalog is used for discovery and target planning;
 * it is not a claim that a source construct can be rewritten without its
 * runtime/provider contract. Features marked with an FCM strategy therefore
 * remain conditional until the source and target behavior has been executed.
 */
final class SpringFeatureCatalog {
    private static final int MAX_OBSERVATIONS_PER_FEATURE = 100;
    private static final Pattern EXACT_VERSION = Pattern.compile("[0-9]+(?:\\.[0-9A-Za-z-]+)*");
    private static final Pattern SPRING_CANDIDATE = Pattern.compile(
            "(?i)org\\.springframework\\.|@(?:SpringBootApplication|Configuration|Controller|Service|Repository|Bean|Autowired|Transactional|RequestMapping|EnableWebSecurity)\\b|spring\\.(?:config|profiles|datasource|jpa|web|security)\\.",
            Pattern.MULTILINE);

    private record Marker(Pattern expression, String label) {
        Marker(String expression, String label) {
            this(Pattern.compile(expression, Pattern.MULTILINE), label);
        }
    }

    record FeatureSpec(
            String id,
            String component,
            String domain,
            List<String> targetApis,
            String targetStrategy,
            List<String> obligations,
            List<Marker> markers
    ) {
        FeatureSpec {
            targetApis = List.copyOf(targetApis);
            obligations = List.copyOf(obligations);
            markers = List.copyOf(markers);
        }
    }

    private static final List<String> COMMON_OBLIGATIONS = List.of(
            "preserve-source-order-and-conditions",
            "bind-to-exact-selected-target-profile",
            "run-source-target-contract-before-promotion");

    /**
     * This is intentionally explicit instead of a dependency-name allowlist.
     * A dependency says that a feature is available; a source observation says
     * that the feature is actually part of the application contract.
     */
    private static final List<FeatureSpec> FEATURES = List.of(
            feature("language-java", "java", "language", "java-21", "java-toolchain-and-openrewrite",
                    "Java source must compile with the exact Java 21 toolchain", "preserve-public-api-and-reflection-signatures",
                    marker("(?s).*", "Java source file")),
            feature("language-kotlin", "kotlin", "language", "kotlin-jvm-21", "kotlin-compiler-and-spring-kotlin-adapter",
                    "Kotlin compiler, nullability metadata and coroutine signatures require a target build",
                    "preserve-suspend-and-reactive-boundaries", marker("(?s).*", "Kotlin source file")),
            feature("language-groovy", "groovy", "language", "groovy-5", "groovy-compiler-and-spring-groovy-adapter",
                    "Groovy dynamic dispatch and AST transforms require a target build", "preserve-runtime-metaprogramming-contract",
                    marker("(?s).*", "Groovy source file")),
            feature("language-configuration", "spring-configuration", "language", "typed-config-and-fcm-emitter",
                    "typed-config-and-fcm-emitter", "preserve-XML-properties-YAML-source-format-and-order",
                    "preserve-profile-placeholder-and-secret-boundaries", marker("(?s).*", "configuration source file")),

            feature("core-bean-di", "spring-core-context", "dependency-injection", "Spring BeanFactory/ApplicationContext",
                    "fcm-bean-graph-emitter", "preserve-bean-names-scopes-qualifiers-and-primary-selection",
                    "preserve-lifecycle-and-proxy-boundaries",
                    marker("@(?:Configuration|Component|Service|Repository|Bean)\\b", "bean declaration"),
                    marker("\\b(?:ApplicationContext|BeanFactory|ObjectProvider)\\b", "context or bean factory API"),
                    marker("\\b(?:Import|ComponentScan|Qualifier|Primary|Lazy)\\b", "DI metadata")),
            feature("core-component-scan", "spring-context", "dependency-injection", "@ComponentScan / typed scan configuration",
                    "fcm-component-scan-emitter", "preserve-include-exclude-filters-and-scan-order",
                    "preserve-configuration-class-proxying", marker("@ComponentScan\\b|<context:component-scan\\b", "component scan")),
            feature("core-profiles-conditions", "spring-context", "configuration", "@Profile / @Conditional",
                    "fcm-conditional-configuration-emitter", "preserve-profile-and-condition-precedence",
                    "do-not-flatten-conditional-beans", marker("@Profile\\b|@Conditional(?:On[A-Za-z]+)?\\b|spring\\.profiles\\.", "profile or condition")),
            feature("core-configuration-properties", "spring-boot", "configuration", "@ConfigurationProperties and Binder",
                    "upstream-openrewrite-plus-configuration-contract", "preserve-relaxed-binding-and-validation",
                    "preserve-property-source-precedence", marker("@ConfigurationProperties\\b|@EnableConfigurationProperties\\b|\\bBinder\\b", "configuration properties binding")),
            feature("core-events", "spring-context", "lifecycle", "ApplicationEventPublisher / @EventListener",
                    "fcm-event-ordering-emitter", "preserve-event-type-and-listener-order",
                    "preserve-transactional-event-phase", marker("@EventListener\\b|ApplicationEventPublisher|ApplicationListener", "application event")),
            feature("core-aop", "spring-aop", "dependency-injection", "Spring AOP proxy/advisor",
                    "fcm-proxy-emitter", "preserve-advisor-order-and-pointcut-boundary",
                    "preserve-proxy-target-class-and-self-invocation-semantics", marker("@Aspect\\b|@Around\\b|@Before\\b|@After(?:Returning|Throwing)?\\b|\\bAdvisor\\b", "AOP advice")),
            feature("core-async", "spring-context", "lifecycle", "@Async / TaskExecutor",
                    "fcm-async-executor-emitter", "preserve-executor-selection-and-rejection-policy",
                    "preserve-security-and-transaction-context-propagation", marker("@Async\\b|@EnableAsync\\b|AsyncConfigurer|TaskExecutor", "async execution")),
            feature("core-resilience", "spring-core-context", "resilience", "@ConcurrencyLimit/@Retryable/RetryTemplate",
                    "spring-framework-7-resilience-target-profile", "preserve-concurrency-limits-retry-backoff-and-jitter",
                    "preserve-exception-classification-idempotency-and-observability", marker("@ConcurrencyLimit\\b|@Retryable\\b|RetryTemplate|RetryOperations", "Spring resilience")),
            feature("core-spel", "spring-expression", "configuration", "SpEL ExpressionParser",
                    "upstream-openrewrite-plus-expression-contract", "preserve-expression-evaluation-context",
                    "preserve-method-access-and-deny-unsafe-evaluation", marker("ExpressionParser|SpelExpression|#\\{[^}]+\\}", "Spring Expression Language")),
            feature("core-resource-message", "spring-core-context", "configuration", "Resource / MessageSource",
                    "fcm-resource-and-locale-emitter", "preserve-resource-resolution-and-encoding",
                    "preserve-locale-fallback-and-message-interpolation", marker("ResourceLoader|ResourceBundleMessageSource|ReloadableResourceBundleMessageSource|\\bMessageSource\\b", "resource or message source")),

            feature("boot-application-bootstrap", "spring-boot", "lifecycle", "SpringApplication / @SpringBootApplication",
                    "upstream-openrewrite-plus-target-profile", "preserveapplication-bootstrap-order-and-banner-policy",
                    "preserve-environment-preparation-and-runner-exit-code", marker("@SpringBootApplication\\b|SpringApplication(?:Builder)?\\b|SpringApplication\\.run\\s*\\(", "Boot application bootstrap")),
            feature("boot-autoconfiguration", "spring-boot", "configuration", "@AutoConfiguration / imports metadata",
                    "upstream-openrewrite-plus-auto-configuration-contract", "preserve-auto-configuration-order-and-conditionality",
                    "preserve-exclusions-and-user-bean-backoff", marker("@(?:EnableAutoConfiguration|AutoConfiguration)\\b|AutoConfiguration\\.imports|spring\\.factories|@ConditionalOn", "auto-configuration")),
            feature("boot-modular-starters", "spring-boot", "build", "Spring Boot modular starters",
                    "boot-4-modular-starter-target-profile", "preserve-starter-boundary-and-transitive-dependency-policy",
                    "preserve-Jackson-3-servlet-reactive-and-test-module-selection", marker("spring-boot-starter-(?:webmvc|webflux|json|jackson|test)\\b", "Boot modular starter")),
            feature("boot-config-data", "spring-boot", "configuration", "ConfigDataEnvironment",
                    "upstream-openrewrite-plus-config-data-contract", "preserve-import-order-and-profile-activation",
                    "preserve-configtree-and-placeholder-failure", marker("spring\\.config\\.(?:import|activate|location|name)|ConfigData|configtree:", "ConfigData")),
            feature("boot-logging", "spring-boot", "operations", "Logback/Log4j2 logging system",
                    "upstream-openrewrite-plus-logging-profile", "preserve-levels-appenders-and-redaction",
                    "preserve-rotation-and-shutdown-flush", marker("logging\\.(?:level|file|pattern|logback|structured)|logback-spring\\.xml|log4j2-spring\\.xml", "Boot logging")),
            feature("boot-file-rotation", "spring-boot", "operations", "Log4j2 size/time/cron file rotation",
                    "boot-4.1.1-log4j-rotation-target-profile", "preserve-rotation-strategy-size-time-cron-and-retention",
                    "preserve-redaction-flush-and-failure-policy", marker("logging\\.log4j2\\.|log4j2.*(?:rotation|rolling|policies)|RollingFile", "Log4j2 file rotation")),
            feature("boot-actuator", "spring-boot-actuator", "operations", "Actuator endpoint/health groups",
                    "fcm-actuator-policy-emitter", "preserve-endpoint-exposure-and-management-port",
                    "preserve-health-readiness-liveness-and-redaction", marker("spring-boot-starter-actuator|management\\.(?:endpoints|endpoint|server)\\.|@(?:Endpoint|ReadOperation|WriteOperation|DeleteOperation)\\b", "Actuator")),
            feature("boot-observability", "spring-boot-actuator", "operations", "ObservationRegistry/Micrometer/OpenTelemetry",
                    "fcm-observation-emitter", "preserve-meter-names-tags-and-cardinality-policy",
                    "preserve-trace-context-and-error-recording", marker("ObservationRegistry|MeterRegistry|@(?:Observed|Timed|Counted)\\b|OpenTelemetry|io\\.micrometer", "observability")),
            feature("boot-graceful-shutdown", "spring-boot", "lifecycle", "server.shutdown=graceful / SmartLifecycle",
                    "upstream-openrewrite-plus-lifecycle-contract", "preserve-drain-timeout-and-in-flight-request-policy",
                    "preserve-destroy-order-and-signal-handling", marker("server\\.shutdown|(?m)^\\s*shutdown\\s*:\\s*graceful\\s*$|spring\\.lifecycle\\.|SmartLifecycle|DisposableBean", "graceful lifecycle")),
            feature("boot-aot-native", "spring-boot", "build", "RuntimeHints / AOT processing",
                    "fcm-aot-hints-emitter", "preserve-reflection-resource-and-proxy-hints",
                    "require-native-or-aot-build-when-source-uses-native-mode", marker("RuntimeHints|RuntimeHintsRegistrar|@ImportRuntimeHints|AotProcessor|native-image", "AOT or native image")),
            feature("boot-null-safety", "spring-boot", "language", "JSpecify nullness and Spring null-safe APIs",
                    "boot-4-nullness-target-profile", "preserve-nullability-annotations-and-Kotlin-metadata",
                    "preserve-null-contracts-at-reflection-and-serialization-boundaries", marker("org\\.jspecify|@NullMarked\\b|@NullUnmarked\\b|@Nullable\\b|@NonNull\\b", "null-safety contract")),
            feature("boot-grpc", "spring-boot-grpc", "integration", "Spring gRPC server/client/test",
                    "boot-4.1.1-grpc-target-profile", "preserve-proto-service-and-interceptor-contract",
                    "preserve-http2-or-netty-transport-and-deadline-policy", marker("spring-boot-grpc-(?:server|client|test)|org\\.springframework\\.grpc|@GrpcService\\b|Grpc(?:Server|Client|Service)|io\\.grpc\\.", "Spring gRPC")),
            feature("boot-jackson", "spring-boot", "web", "Jackson 3 Boot configuration",
                    "boot-4.1.1-jackson-target-profile", "preserve-module-registration-and-property-naming",
                    "preserve-null-unknown-property-and-date-serialization-policy", marker("Jackson2ObjectMapperBuilder|ObjectMapper|JsonMapper|JsonMapperBuilderCustomizer|tools\\.jackson|spring\\.jackson\\.", "Jackson configuration")),

            feature("mvc-annotated-endpoints", "spring-webmvc", "web", "@Controller/@RequestMapping MVC endpoint",
                    "fcm-mvc-route-emitter", "preserve-path-method-media-type-and-parameter-contract",
                    "preserve-handler-order-and-content-negotiation", marker("@(?:Controller|RestController|RequestMapping|GetMapping|PostMapping|PutMapping|PatchMapping|DeleteMapping)\\b", "annotated MVC endpoint")),
            feature("mvc-binding-validation", "spring-webmvc", "validation", "WebDataBinder / Jakarta Validation",
                    "fcm-mvc-binding-emitter", "preserve-conversion-binding-errors-and-validation-groups",
                    "preserve-400-error-shape-and-message-locale", marker("@(?:RequestParam|PathVariable|RequestBody|ModelAttribute|Valid|Validated)\\b|WebDataBinder|Validator", "MVC binding and validation")),
            feature("mvc-error-handling", "spring-webmvc", "web", "ControllerAdvice / HandlerExceptionResolver",
                    "fcm-mvc-error-emitter", "preserve-advice-order-status-and-content-type",
                    "preserve-exception-disclosure-and-logging-policy", marker("@(?:ControllerAdvice|RestControllerAdvice|ExceptionHandler)\\b|HandlerExceptionResolver", "MVC error handling")),
            feature("mvc-filters-interceptors", "spring-webmvc", "web", "Servlet Filter / HandlerInterceptor",
                    "fcm-servlet-order-emitter", "preserve-filter-interceptor-order-and-dispatch-types",
                    "preserve-security-cors-encoding-and-body-caching-semantics", marker("FilterRegistrationBean|OncePerRequestFilter|HandlerInterceptor|WebMvcConfigurer|web\\.xml", "MVC filters or interceptors")),
            feature("mvc-view-resources", "spring-webmvc", "web", "ViewResolver/JSP/Thymeleaf/static resources",
                    "fcm-view-emitter-or-blocked-profile", "preserve-view-resolver-order-prefix-suffix-and-model",
                    "preserve-static-resource-cache-and-welcome-path", marker("ViewResolver|InternalResourceViewResolver|ThymeleafViewResolver|WEB-INF/views|\\.jsp\\b|addResourceHandlers", "MVC views or resources")),
            feature("mvc-multipart-cors", "spring-webmvc", "web", "MultipartResolver / CORS",
                    "fcm-multipart-cors-emitter", "preserve-size-limits-temp-storage-and-file-cleanup",
                    "preserve-origin-method-header-and-credential-policy", marker("MultipartResolver|MultipartFile|spring\\.servlet\\.multipart\\.|@CrossOrigin|CorsConfiguration", "MVC multipart or CORS")),
            feature("mvc-websocket-stomp", "spring-websocket", "messaging", "WebSocket/STOMP",
                    "fcm-websocket-emitter", "preserve-handshake-interceptors-destinations-and-user-destination",
                    "preserve-heartbeat-backpressure-and-close-semantics", marker("@EnableWebSocket(?:MessageBroker)?\\b|WebSocketHandler|StompEndpointRegistry|SimpMessagingTemplate", "WebSocket or STOMP")),
            feature("webflux-reactive-endpoints", "spring-webflux", "web", "RouterFunction/WebFilter/Mono/Flux",
                    "fcm-webflux-route-emitter", "preserve-reactive-backpressure-cancellation-and-scheduler",
                    "preserve-status-header-body-and-error-signals", marker("spring-webflux|@EnableWebFlux\\b|RouterFunction|HandlerFunction|WebFilter|\\b(?:Mono|Flux)<", "WebFlux")),
            feature("web-client", "spring-web", "integration", "RestClient/WebClient/HTTP interface",
                    "boot-4.1.1-http-client-target-profile", "preserve-timeouts-retries-redirects-and-proxy-policy",
                    "preserve-SSRF-filter-and-trust-boundary", marker("RestTemplate|RestClient|WebClient|HttpServiceProxyFactory|InetAddressFilter", "Spring HTTP client")),
            feature("web-rsocket", "spring-messaging", "messaging", "RSocketRequester/RSocket responder",
                    "fcm-rsocket-emitter", "preserve-route-metadata-backpressure-and-resume-policy",
                    "preserve-transport-authentication-and-cancellation", marker("RSocketRequester|RSocketStrategies|@ConnectMapping|rsocket\\.", "RSocket")),
            feature("web-graphql", "spring-graphql", "web", "GraphQL controller/schema/data fetcher",
                    "fcm-graphql-schema-emitter", "preserve-schema-nullability-query-cost-and-error-paths",
                    "preserve-field-authorization-batching-and-subscription-lifecycle", marker("@(?:QueryMapping|MutationMapping|SubscriptionMapping)\\b|GraphQlSource|graphql\\.schema|spring-graphql", "Spring GraphQL")),
            feature("web-hateoas", "spring-hateoas", "web", "RepresentationModel and link relations",
                    "fcm-hateoas-representation-emitter", "preserve-link-relations-affordances-and-media-types",
                    "preserve-collection-pagination-and-authorization-filtering", marker("RepresentationModel|EntityModel|CollectionModel|RepresentationModelAssembler|spring-hateoas", "Spring HATEOAS")),

            feature("data-jpa", "spring-data-jpa", "persistence", "Jakarta Persistence/Hibernate ORM",
                    "fcm-jpa-provider-emitter", "preserve-entity-column-fetch-cascade-and-locking",
                    "preserve-query-flush-schema-and-exception-timing", marker("@(?:Entity|MappedSuperclass|Embeddable|Converter)\\b|JpaRepository|EntityManager|@EnableJpaRepositories", "JPA")),
            feature("data-jdbc", "spring-data-jdbc", "persistence", "JdbcTemplate/Spring Data JDBC",
                    "fcm-jdbc-provider-emitter", "preserve-SQL-parameter-result-and-null-mapping",
                    "preserve-pool-timeouts-and-exception-translation", marker("JdbcTemplate|NamedParameterJdbcTemplate|RowMapper|@MappedCollection|@EnableJdbcRepositories", "JDBC")),
            feature("data-r2dbc", "spring-data-r2dbc", "persistence", "R2dbcEntityTemplate/DatabaseClient",
                    "fcm-r2dbc-provider-emitter", "preserve-reactive-transaction-and-backpressure-boundaries",
                    "preserve-bindings-nullability-and-driver-codecs", marker("spring-data-r2dbc|DatabaseClient|R2dbcEntityTemplate|R2dbcRepository|@EnableR2dbcRepositories", "R2DBC")),
            feature("data-redis", "spring-data-redis", "persistence", "RedisTemplate/Redis repositories",
                    "fcm-redis-provider-emitter", "preserve-keyspace-serialization-ttl-and-cluster-policy",
                    "preserve-pubsub-stream-and-lock-semantics", marker("RedisTemplate|StringRedisTemplate|RedisRepository|spring\\.data\\.redis\\.", "Redis")),
            feature("data-document", "spring-data-document", "persistence", "MongoDB/Elasticsearch document repositories",
                    "fcm-document-provider-emitter", "preserve-document-id-index-and-converter-semantics",
                    "preserve-query-consistency-and retry policy", marker("MongoTemplate|MongoRepository|ElasticsearchClient|ElasticsearchRepository|@Document|spring\\.data\\.(?:mongodb|elasticsearch)\\.", "document database")),
            feature("transactions", "spring-tx", "transaction", "@Transactional/TransactionTemplate",
                    "fcm-transaction-emitter", "preserve-propagation-isolation-read-only-timeout-and-rollback",
                    "preserve-manager-selection-resource-binding-and-self-invocation-boundary", marker("@Transactional\\b|PlatformTransactionManager|TransactionTemplate|@EnableTransactionManagement|JtaTransactionManager", "transaction")),

            feature("messaging-kafka", "spring-kafka", "messaging", "KafkaTemplate/@KafkaListener",
                    "fcm-kafka-provider-emitter", "preserve-topic-partition-group-ack-and-retry-policy",
                    "preserve-schema-headers-ordering-and-duplicate-effects", marker("@KafkaListener\\b|KafkaTemplate|KafkaListenerContainerFactory|spring\\.kafka\\.", "Kafka")),
            feature("messaging-amqp", "spring-amqp", "messaging", "RabbitTemplate/@RabbitListener",
                    "fcm-amqp-provider-emitter", "preserve-exchange-routing-key-ack-and-dead-letter-policy",
                    "preserve-retry-redelivery-ordering-and-transaction-boundary", marker("@RabbitListener\\b|RabbitTemplate|RabbitListenerContainerFactory|spring\\.rabbitmq\\.", "AMQP")),
            feature("messaging-jms", "spring-jms", "messaging", "JmsTemplate/@JmsListener",
                    "fcm-jms-provider-emitter", "preserve-destination-ack-selector-and-session-policy",
                    "preserve-redelivery-ordering-and-XA-boundary", marker("@JmsListener\\b|JmsTemplate|JmsListenerContainerFactory|spring\\.(?:jms|artemis|activemq)\\.", "JMS")),
            feature("messaging-integration", "spring-integration", "messaging", "IntegrationFlow/MessageChannel",
                    "fcm-integration-flow-emitter", "preserve-channel-router-transformer-and-error-flow-order",
                    "preserve poller retry transaction and idempotency semantics", marker("@IntegrationComponentScan\\b|IntegrationFlow|MessageChannel|MessageEndpoint|@ServiceActivator\\b|spring\\.integration\\.", "Spring Integration")),
            feature("messaging-batch", "spring-batch", "messaging", "Job/Step/ItemReader",
                    "fcm-batch-job-emitter", "preserve-job-repository-instance-and-restartability",
                    "preserve chunk transaction skip retry and listener order", marker("@EnableBatchProcessing\\b|JobRepository|JobLauncher|ItemReader|ItemProcessor|ItemWriter|StepBuilder", "Spring Batch")),
            feature("integration-ldap-session", "spring-ldap-session", "integration", "LdapTemplate/session repository",
                    "exact-provider-profile-required", "preserve-directory-schema-bind-search-and-paging-policy",
                    "preserve-session-index-expiry-concurrency-and-security-boundary", marker("LdapTemplate|@EnableLdapRepositories|spring\\.ldap\\.|spring\\.session\\.|SessionRepository", "LDAP or Spring Session")),
            feature("cache", "spring-cache", "cache", "@Cacheable/CacheManager",
                    "fcm-cache-provider-emitter", "preserve-cache-name-key-generator-condition-and-unless",
                    "preserve-ttl-serialization-null-and-eviction-order", marker("@(?:Cacheable|CachePut|CacheEvict|Caching)\\b|@EnableCaching\\b|CacheManager|spring\\.cache\\.", "cache")),
            feature("scheduler", "spring-context-quartz", "scheduler", "@Scheduled/Quartz",
                    "fcm-scheduler-provider-emitter", "preserve-cron-rate-delay-timezone-and-overlap-policy",
                    "preserve-misfire-startup-shutdown-and-context propagation", marker("@Scheduled\\b|@EnableScheduling\\b|TaskScheduler|SchedulerFactoryBean|QuartzJobBean|spring\\.(?:task\\.scheduling|quartz)\\.", "scheduler")),
            feature("security-web", "spring-security", "security", "SecurityFilterChain/AuthorizationManager",
                    "fcm-security-policy-emitter", "preserve-filter-order-csrf-cors-session-and-request-cache",
                    "preserve-deny-by-default-and-access-denied-contract", marker("SecurityFilterChain|HttpSecurity|WebSecurityConfigurerAdapter|authorizeHttpRequests|requestMatchers|@EnableWebSecurity\\b", "Spring Security")),
            feature("security-method-oauth2", "spring-security-oauth2", "security", "method security/OAuth2/OIDC",
                    "fcm-security-provider-emitter", "preserve-token-issuer-audience-scope-and-role-mapping",
                    "preserve-method-proxy-boundaries-and-authentication-failure", marker("@(?:PreAuthorize|PostAuthorize|Secured|RolesAllowed)\\b|oauth2Login|oauth2ResourceServer|JwtDecoder|ClientRegistration|@EnableMethodSecurity\\b", "method security or OAuth2")),
            feature("testing-spring", "spring-test", "testing", "SpringBootTest/MVC/WebFlux test slices",
                    "upstream-openrewrite-plus-test-integrity", "preserve-test-scope-context-caching-and-security-test-fixtures",
                    "preserve-test-identities-and-negative-assertions", marker("@SpringBootTest\\b|@(?:WebMvcTest|WebFluxTest|DataJpaTest|JsonTest|MockBean)\\b|MockMvc|WebTestClient", "Spring test")),
            feature("testing-container", "testcontainers", "testing", "Testcontainers integration",
                    "target-test-toolchain-and-provider-profile", "preserve-container-image-digest-and-network-isolation",
                    "preserve-test-data-cleanup-and-reproducibility", marker("org\\.testcontainers|@Testcontainers\\b|@Container\\b", "Testcontainers")),
            feature("testing-spock-groovy", "spock", "testing", "Spock 2.4 with Groovy 5",
                    "boot-4.1.1-spock-groovy-target-profile", "preserve-specification-lifecycle-data-driven-and-mock-interactions",
                    "preserve-Groovy-5-compiler-and-test-runtime-boundary", marker("spock\\.lang|extends\\s+Specification|given:|when:|then:", "Spock/Groovy test")),
            feature("unmapped-spring-construct", "spring-unknown", "unsupported", "source construct retained with explicit blocker",
                    "unsupported-preserve-and-report", "preserve-unmapped-source-bytes-and-provenance",
                    "require-human-or-provider-specific-target-mapping-before-execution", marker("(?s).*", "unmapped Spring construct"))
    );

    private SpringFeatureCatalog() {}

    static List<FeatureSpec> specs() {
        return FEATURES;
    }

    static FeatureSpec spec(String id) {
        return FEATURES.stream().filter(feature -> feature.id().equals(id)).findFirst().orElse(null);
    }

    static List<FeatureObservation> observe(Path file, String relative, String content,
                                            SpringCapabilityFingerprint.EvidenceState state,
                                            List<String> conditions) {
        String language = language(file);
        List<FeatureObservation> observations = new ArrayList<>();
        if (language != null) {
            String id = "language-" + language;
            FeatureSpec languageSpec = spec(id);
            if (languageSpec != null) {
                observations.add(observation(languageSpec, state, language,
                        List.of(trace(state, relative, 1, "source-language", conditions))));
            }
        }
        for (FeatureSpec feature : FEATURES) {
            if (feature.id().startsWith("language-") || feature.id().equals("unmapped-spring-construct")) continue;
            for (Marker marker : feature.markers()) {
                Matcher matcher = marker.expression().matcher(content);
                if (!matcher.find()) continue;
                int line = lineNumber(content, matcher.start());
                observations.add(observation(feature, state,
                        language == null ? "configuration" : language,
                        List.of(trace(state, relative, line, marker.label(), conditions))));
                break;
            }
        }
        boolean knownFeatureObserved = observations.stream()
                .anyMatch(observation -> !observation.id().startsWith("language-"));
        if (!knownFeatureObserved && SPRING_CANDIDATE.matcher(content).find()) {
            FeatureSpec unknown = spec("unmapped-spring-construct");
            observations.add(observation(unknown, SpringCapabilityFingerprint.EvidenceState.UNKNOWN,
                    language == null ? "configuration" : language,
                    List.of(trace(SpringCapabilityFingerprint.EvidenceState.UNKNOWN, relative, 1,
                            "unmapped Spring construct", conditions))));
        }
        return List.copyOf(observations);
    }

    static List<FeatureObservation> merge(List<FeatureObservation> base,
                                          List<FeatureObservation> additions) {
        Map<String, MutableObservation> merged = new TreeMap<>();
        for (FeatureObservation observation : base) merged.computeIfAbsent(observation.id(),
                ignored -> new MutableObservation(observation)).add(observation);
        for (FeatureObservation observation : additions) merged.computeIfAbsent(observation.id(),
                ignored -> new MutableObservation(observation)).add(observation);
        return merged.values().stream().map(MutableObservation::toRecord)
                .sorted(Comparator.comparing(FeatureObservation::id)).toList();
    }

    static List<Map<String, Object>> render(List<FeatureObservation> observations,
                                             String targetBoot,
                                             String targetJava) {
        if (targetBoot == null || !EXACT_VERSION.matcher(targetBoot).matches()) {
            throw new IllegalArgumentException("targetBoot must be an exact version");
        }
        if (targetJava == null || !EXACT_VERSION.matcher(targetJava).matches()) {
            throw new IllegalArgumentException("targetJava must be an exact version");
        }
        String target = "spring-boot-" + targetBoot;
        String targetObligation = "bind-to-exact-spring-boot-" + targetBoot
                + "-java-" + targetJava + "-profile";
        Map<String, FeatureObservation> unique = new LinkedHashMap<>();
        for (FeatureObservation observation : observations) unique.put(observation.id(), observation);
        List<Map<String, Object>> rendered = new ArrayList<>();
        for (FeatureObservation observation : unique.values()) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("id", observation.id());
            item.put("component", observation.component());
            item.put("domain", observation.domain());
            item.put("evidence_state", observation.evidenceState());
            item.put("source_languages", observation.sourceLanguages());
            item.put("source_traces", observation.sourceTraces());
            item.put("target", target);
            item.put("target_apis", observation.targetApis());
            boolean incompatibleBoot4Strategy = !targetBoot.startsWith("4.")
                    && (observation.targetStrategy().contains("boot-4")
                    || observation.targetStrategy().contains("4.1.1")
                    || observation.targetStrategy().contains("spring-framework-7"));
            item.put("target_strategy", incompatibleBoot4Strategy
                    ? "blocked-incompatible-target-strategy:" + observation.targetStrategy()
                    : observation.targetStrategy());
            item.put("target_applicability", incompatibleBoot4Strategy ? "blocked" : "applicable");
            item.put("obligations", observation.obligations().stream()
                    .map(value -> value.equals("bind-to-exact-selected-target-profile")
                            ? targetObligation : value)
                    .toList());
            rendered.add(item);
        }
        return List.copyOf(rendered);
    }

    private static FeatureObservation observation(FeatureSpec spec,
                                                  SpringCapabilityFingerprint.EvidenceState state,
                                                  String language,
                                                  List<String> traces) {
        List<String> obligations = new ArrayList<>(COMMON_OBLIGATIONS);
        obligations.addAll(spec.obligations());
        return new FeatureObservation(spec.id(), spec.component(), spec.domain(), state.wireValue(),
                List.of(language), traces, spec.targetApis(), spec.targetStrategy(),
                obligations.stream().distinct().toList());
    }

    private static String language(Path file) {
        String name = file.getFileName().toString().toLowerCase(Locale.ROOT);
        if (name.endsWith(".java")) return "java";
        if (name.endsWith(".kt")) return "kotlin";
        if (name.endsWith(".groovy")) return "groovy";
        if (name.endsWith(".xml") || name.endsWith(".properties")
                || name.endsWith(".yml") || name.endsWith(".yaml")) return "configuration";
        return null;
    }

    private static String trace(SpringCapabilityFingerprint.EvidenceState state, String relative,
                                int line, String label, List<String> conditions) {
        StringBuilder value = new StringBuilder()
                .append(state.wireValue()).append("|source|")
                .append(relative.replace('|', '/')).append(':').append(line).append('|').append(label);
        if (!conditions.isEmpty()) value.append("|conditions=").append(String.join(",", conditions));
        return value.toString();
    }

    private static int lineNumber(String content, int offset) {
        int line = 1;
        for (int index = 0; index < Math.min(offset, content.length()); index++) {
            if (content.charAt(index) == '\n') line++;
        }
        return line;
    }

    private static FeatureSpec feature(String id, String component, String domain,
                                       String targetApi, String targetStrategy,
                                       String obligation, String secondObligation,
                                       Marker... markers) {
        return new FeatureSpec(id, component, domain, List.of(targetApi), targetStrategy,
                List.of(obligation, secondObligation), List.of(markers));
    }

    private static Marker marker(String expression, String label) {
        return new Marker(expression, label);
    }

    private static final class MutableObservation {
        private final String id;
        private final String component;
        private final String domain;
        private String evidenceState;
        private final Set<String> languages = new java.util.TreeSet<>();
        private final Set<String> traces = new java.util.TreeSet<>();
        private final List<String> targetApis;
        private final String targetStrategy;
        private final List<String> obligations;

        private MutableObservation(FeatureObservation initial) {
            id = initial.id();
            component = initial.component();
            domain = initial.domain();
            evidenceState = initial.evidenceState();
            targetApis = initial.targetApis();
            targetStrategy = initial.targetStrategy();
            obligations = initial.obligations();
        }

        void add(FeatureObservation observation) {
            languages.addAll(observation.sourceLanguages());
            traces.addAll(observation.sourceTraces());
            evidenceState = strongest(evidenceState, observation.evidenceState());
        }

        FeatureObservation toRecord() {
            return new FeatureObservation(id, component, domain, evidenceState,
                    languages.stream().toList(), traces.stream().limit(MAX_OBSERVATIONS_PER_FEATURE).toList(),
                    targetApis, targetStrategy, obligations);
        }

        private static String strongest(String left, String right) {
            List<String> order = List.of("observed", "conditional", "generated", "test-only", "declared-only", "unknown");
            return order.indexOf(left) <= order.indexOf(right) ? left : right;
        }
    }
}
