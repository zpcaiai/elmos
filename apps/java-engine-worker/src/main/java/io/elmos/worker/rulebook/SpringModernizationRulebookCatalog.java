package io.elmos.worker.rulebook;

import java.util.*;
import java.util.stream.Collectors;

/**
 * Enterprise Modernization Rulebook Catalog.
 * <p>
 * Contains 150 comprehensive, industrial-grade transformation rules across Security,
 * JPA/Hibernate, Spring Cloud, XML-to-JavaConfig, Core Framework, and Actuator/Observability.
 */
public final class SpringModernizationRulebookCatalog {

    public enum RuleCategory {
        SECURITY("Spring Security 5/6 Modernization"),
        JPA_HIBERNATE("JPA & Hibernate 6 Migration"),
        SPRING_CLOUD("Spring Cloud & Microservices Modernization"),
        XML_JAVACONFIG("XML Configuration to JavaConfig Modernization"),
        CORE_FRAMEWORK("Spring Framework 6 & Core Web Modernization"),
        ACTUATOR_OBSERVABILITY("Actuator, Observability, and Runtime Hardening");

        private final String displayName;

        RuleCategory(String displayName) {
            this.displayName = displayName;
        }

        public String getDisplayName() {
            return displayName;
        }
    }

    public enum RuleSeverity {
        BLOCKER(5),
        CRITICAL(4),
        MAJOR(3),
        MINOR(2),
        INFO(1);

        private final int priorityWeight;

        RuleSeverity(int priorityWeight) {
            this.priorityWeight = priorityWeight;
        }

        public int getPriorityWeight() {
            return priorityWeight;
        }
    }

    public record ModernizationRule(
            String ruleId,
            RuleCategory category,
            String name,
            RuleSeverity severity,
            int effortHours,
            String description,
            String sourcePattern,
            String targetTemplate,
            String recipeOrModernizerClass,
            String remediationGuidance,
            String rollbackProcedure,
            String documentationUrl
    ) {
        public boolean matches(String sourceContent) {
            if (sourceContent == null || sourceContent.isEmpty() || sourcePattern == null || sourcePattern.isEmpty()) {
                return false;
            }
            return sourceContent.contains(sourcePattern);
        }
    }

    public record CatalogStatistics(
            int totalRules,
            int totalEffortHours,
            Map<RuleCategory, Integer> countByCategory,
            Map<RuleSeverity, Integer> countBySeverity
    ) {}

    private static final Map<String, ModernizationRule> RULES_BY_ID = new LinkedHashMap<>();
    private static final Map<RuleCategory, List<ModernizationRule>> RULES_BY_CATEGORY = new EnumMap<>(RuleCategory.class);

    static {
        initSecurityRules();
        initJpaRules();
        initCloudRules();
        initXmlRules();
        initCoreRules();
        initActuatorRules();
    }

    private static void initSecurityRules() {
        register(new ModernizationRule(
                "SEC-001",
                RuleCategory.SECURITY,
                "WebSecurityConfigurerAdapter Deprecation Removal",
                RuleSeverity.BLOCKER,
                4,
                "WebSecurityConfigurerAdapter has been completely removed in Spring Security 6.x. Security configurations must declare a @Bean SecurityFilterChain instead.",
                "extends WebSecurityConfigurerAdapter",
                "@Bean\npublic SecurityFilterChain filterChain(HttpSecurity http) throws Exception {\n    return http.build();\n}",
                "io.elmos.recipes.security.SpringSecurityFilterChainRecipe",
                "Eliminate inheritance from WebSecurityConfigurerAdapter and provide a SecurityFilterChain bean.",
                "Revert to WebSecurityConfigurerAdapter if targeting Spring Boot 2.7.x maintenance.",
                "https://docs.spring.io/spring-security/reference/servlet/configuration/java.html"
        ));
        register(new ModernizationRule(
                "SEC-002",
                RuleCategory.SECURITY,
                "AuthorizeRequests to AuthorizeHttpRequests Lambda DSL",
                RuleSeverity.BLOCKER,
                3,
                "authorizeRequests() is deprecated and replaced by authorizeHttpRequests() which provides finer-grained authorization and better performance using AuthorizationManager.",
                "http.authorizeRequests().anyRequest().authenticated()",
                "http.authorizeHttpRequests(auth -> auth.anyRequest().authenticated())",
                "io.elmos.recipes.security.SpringSecurityFilterChainRecipe",
                "Migrate chained authorizeRequests() to lambda-based authorizeHttpRequests(auth -> ...).",
                "Keep authorizeRequests() on Boot 2.7 with chained calls.",
                "https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html"
        ));
        register(new ModernizationRule(
                "SEC-003",
                RuleCategory.SECURITY,
                "AntMatchers to RequestMatchers Migration",
                RuleSeverity.CRITICAL,
                2,
                "antMatchers() and mvcMatchers() are deprecated in favor of requestMatchers() which automatically uses PathPatternParser under Spring MVC.",
                "http.authorizeRequests().antMatchers(\"/api/**\").hasRole(\"ADMIN\")",
                "http.authorizeHttpRequests(auth -> auth.requestMatchers(\"/api/**\").hasRole(\"ADMIN\"))",
                "io.elmos.recipes.security.SpringSecurityFilterChainRecipe",
                "Replace all antMatchers(...) calls with requestMatchers(...).",
                "Restore antMatchers if running on legacy AntPathMatcher engine.",
                "https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html#matchers"
        ));
        register(new ModernizationRule(
                "SEC-004",
                RuleCategory.SECURITY,
                "EnableGlobalMethodSecurity to EnableMethodSecurity",
                RuleSeverity.MAJOR,
                2,
                "@EnableGlobalMethodSecurity is deprecated in favor of @EnableMethodSecurity which activates Pre/Post annotations by default.",
                "@EnableGlobalMethodSecurity(prePostEnabled = true)",
                "@EnableMethodSecurity",
                "io.elmos.recipes.security.SpringSecurityMethodSecurityRecipe",
                "Replace @EnableGlobalMethodSecurity with @EnableMethodSecurity on configuration classes.",
                "Revert annotation back to @EnableGlobalMethodSecurity.",
                "https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html"
        ));
        register(new ModernizationRule(
                "SEC-005",
                RuleCategory.SECURITY,
                "AuthenticationManagerBuilder to @Bean AuthenticationManager",
                RuleSeverity.CRITICAL,
                3,
                "Configuring AuthenticationManagerBuilder via configure(AuthenticationManagerBuilder) is deprecated in favor of exposing an AuthenticationManager @Bean.",
                "protected void configure(AuthenticationManagerBuilder auth) { auth.userDetailsService(...); }",
                "@Bean\npublic AuthenticationManager authenticationManager(AuthenticationConfiguration config) throws Exception {\n    return config.getAuthenticationManager();\n}",
                "io.elmos.recipes.security.SpringSecurityAuthenticationRecipe",
                "Declare AuthenticationManager as a @Bean using AuthenticationConfiguration or DaoAuthenticationProvider.",
                "Restore configure(AuthenticationManagerBuilder) override.",
                "https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html"
        ));
        register(new ModernizationRule(
                "SEC-006",
                RuleCategory.SECURITY,
                "OAuth2 Resource Server JWT Configuration Modernization",
                RuleSeverity.CRITICAL,
                4,
                "OAuth2 Resource Server DSL requires modern lambda-based jwt configuration to eliminate deprecated chained builders.",
                "http.oauth2ResourceServer().jwt()",
                "http.oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))",
                "io.elmos.recipes.security.SpringSecurityOAuth2ResourceServerRecipe",
                "Upgrade oauth2ResourceServer() invocation to lambda DSL.",
                "Keep chained oauth2ResourceServer().jwt() call.",
                "https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html"
        ));
        register(new ModernizationRule(
                "SEC-007",
                RuleCategory.SECURITY,
                "CSRF CookieRepository and Custom Matcher Configuration",
                RuleSeverity.MAJOR,
                2,
                "CSRF configuration requires lambda DSL and modern CookieCsrfTokenRepository.withHttpOnlyFalse() for SPA integration.",
                "http.csrf().csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())",
                "http.csrf(csrf -> csrf.csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse()))",
                "io.elmos.recipes.security.SpringSecurityCsrfCookieRepositoryRecipe",
                "Refactor csrf() chain into lambda block.",
                "Restore csrf() chained builder.",
                "https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html"
        ));
        register(new ModernizationRule(
                "SEC-008",
                RuleCategory.SECURITY,
                "CORS Configuration Source Bean Registration",
                RuleSeverity.MAJOR,
                2,
                "CORS configuration requires CorsConfigurationSource @Bean and lambda-based cors(Customizer.withDefaults()) on HttpSecurity.",
                "http.cors().and()",
                "http.cors(Customizer.withDefaults())",
                "io.elmos.recipes.security.SpringSecurityCorsConfigurationRecipe",
                "Provide CorsConfigurationSource @Bean and invoke http.cors(Customizer.withDefaults()).",
                "Restore chained http.cors().",
                "https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html"
        ));
        register(new ModernizationRule(
                "SEC-009",
                RuleCategory.SECURITY,
                "SessionManagement Stateless Policy Configuration",
                RuleSeverity.MAJOR,
                2,
                "Chained sessionManagement() must be migrated to sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS)).",
                "http.sessionManagement().sessionCreationPolicy(SessionCreationPolicy.STATELESS)",
                "http.sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))",
                "io.elmos.recipes.security.SpringSecuritySessionManagementRecipe",
                "Convert sessionManagement chained call to lambda DSL.",
                "Restore chained sessionManagement() call.",
                "https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html"
        ));
        register(new ModernizationRule(
                "SEC-010",
                RuleCategory.SECURITY,
                "Custom Filter Chain Order Registration",
                RuleSeverity.CRITICAL,
                3,
                "Custom filters added via addFilterBefore/addFilterAfter must be explicitly typed and not registered as generic Spring @Beans to prevent duplicate servlet execution.",
                "@Bean public CustomAuthFilter customAuthFilter() { return new CustomAuthFilter(); }",
                "// Inject into SecurityFilterChain without @Bean or register with FilterRegistrationBean(enabled = false)",
                "io.elmos.recipes.security.SpringSecurityCustomFilterOrderRecipe",
                "Disable servlet auto-registration for custom Spring Security filters.",
                "Re-expose filter as generic Servlet bean.",
                "https://docs.spring.io/spring-security/reference/servlet/architecture.html#servlet-filters-review"
        ));
        register(new ModernizationRule(
                "SEC-011",
                RuleCategory.SECURITY,
                "FormLogin Lambda DSL Migration",
                RuleSeverity.MINOR,
                1,
                "Migrate formLogin().loginPage(...).permitAll() to lambda DSL formLogin(form -> form.loginPage(...).permitAll()).",
                "http.formLogin().loginPage(\"/login\").permitAll()",
                "http.formLogin(form -> form.loginPage(\"/login\").permitAll())",
                "io.elmos.worker.security.SpringSecurityFilterChainModernizer",
                "Refactor formLogin call to lambda format.",
                "Restore chained formLogin.",
                "https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html"
        ));
        register(new ModernizationRule(
                "SEC-012",
                RuleCategory.SECURITY,
                "HttpBasic Lambda DSL Migration",
                RuleSeverity.MINOR,
                1,
                "Migrate httpBasic().and() to httpBasic(Customizer.withDefaults()).",
                "http.httpBasic().and()",
                "http.httpBasic(Customizer.withDefaults())",
                "io.elmos.worker.security.SpringSecurityFilterChainModernizer",
                "Replace httpBasic chained builder with lambda Customizer.",
                "Restore chained httpBasic.",
                "https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html"
        ));
        register(new ModernizationRule(
                "SEC-013",
                RuleCategory.SECURITY,
                "Logout SuccessHandler Lambda Configuration",
                RuleSeverity.MINOR,
                1,
                "Migrate logout().logoutUrl(...).logoutSuccessUrl(...) to logout(logout -> logout.logoutUrl(...)).",
                "http.logout().logoutUrl(\"/logout\").logoutSuccessUrl(\"/\")",
                "http.logout(logout -> logout.logoutUrl(\"/logout\").logoutSuccessUrl(\"/\"))",
                "io.elmos.worker.security.SpringSecurityFilterChainModernizer",
                "Wrap logout configurations in modern lambda DSL.",
                "Restore logout chained builder.",
                "https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html"
        ));
        register(new ModernizationRule(
                "SEC-014",
                RuleCategory.SECURITY,
                "ExceptionHandling AuthenticationEntryPoint Lambda",
                RuleSeverity.MAJOR,
                2,
                "Migrate exceptionHandling().authenticationEntryPoint(...) to exceptionHandling(ex -> ex.authenticationEntryPoint(...)).",
                "http.exceptionHandling().authenticationEntryPoint(new CustomEntryPoint())",
                "http.exceptionHandling(ex -> ex.authenticationEntryPoint(new CustomEntryPoint()))",
                "io.elmos.worker.security.SpringSecurityFilterChainModernizer",
                "Refactor exceptionHandling to lambda DSL.",
                "Restore chained exceptionHandling.",
                "https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html"
        ));
        register(new ModernizationRule(
                "SEC-015",
                RuleCategory.SECURITY,
                "Headers FrameOptions / HSTS Security Policy",
                RuleSeverity.MAJOR,
                2,
                "Migrate headers().frameOptions().sameOrigin() to headers(headers -> headers.frameOptions(HeadersConfigurer.FrameOptionsConfig::sameOrigin)).",
                "http.headers().frameOptions().sameOrigin()",
                "http.headers(headers -> headers.frameOptions(HeadersConfigurer.FrameOptionsConfig::sameOrigin))",
                "io.elmos.worker.security.SpringSecurityFilterChainModernizer",
                "Convert headers chained call to lambda format.",
                "Restore chained headers.",
                "https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html"
        ));
        register(new ModernizationRule(
                "SEC-016",
                RuleCategory.SECURITY,
                "Anonymous Authentication Filter Customization",
                RuleSeverity.INFO,
                1,
                "Configure anonymous authentication via anonymous(anonymous -> anonymous.principal(...)).",
                "http.anonymous().principal(\"guest\")",
                "http.anonymous(anonymous -> anonymous.principal(\"guest\"))",
                "io.elmos.worker.security.SpringSecurityFilterChainModernizer",
                "Use anonymous lambda customizer.",
                "Restore chained anonymous call.",
                "https://docs.spring.io/spring-security/reference/servlet/authentication/anonymous.html"
        ));
        register(new ModernizationRule(
                "SEC-017",
                RuleCategory.SECURITY,
                "SecurityExpressionHandler Method Authorization",
                RuleSeverity.MAJOR,
                3,
                "DefaultMethodSecurityExpressionHandler registration in Spring Security 6 must be wired via MethodSecurityExpressionHandler @Bean.",
                "class CustomSecurityConfig extends GlobalMethodSecurityConfiguration",
                "@Bean\nstatic MethodSecurityExpressionHandler methodSecurityExpressionHandler() { return new DefaultMethodSecurityExpressionHandler(); }",
                "io.elmos.worker.security.SpringSecurityFilterChainModernizer",
                "Declare MethodSecurityExpressionHandler as a static @Bean.",
                "Restore GlobalMethodSecurityConfiguration inheritance.",
                "https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html"
        ));
        register(new ModernizationRule(
                "SEC-018",
                RuleCategory.SECURITY,
                "RememberMe Services Persistent Token Repository",
                RuleSeverity.MAJOR,
                2,
                "Migrate rememberMe().tokenRepository(...) to rememberMe(remember -> remember.tokenRepository(...)).",
                "http.rememberMe().tokenRepository(persistentTokenRepository())",
                "http.rememberMe(remember -> remember.tokenRepository(persistentTokenRepository()))",
                "io.elmos.worker.security.SpringSecurityFilterChainModernizer",
                "Convert rememberMe configuration to lambda DSL.",
                "Restore chained rememberMe call.",
                "https://docs.spring.io/spring-security/reference/servlet/authentication/rememberme.html"
        ));
        register(new ModernizationRule(
                "SEC-019",
                RuleCategory.SECURITY,
                "DaoAuthenticationProvider PasswordEncoder Wiring",
                RuleSeverity.CRITICAL,
                2,
                "DaoAuthenticationProvider requires explicit PasswordEncoder and UserDetailsService assignment.",
                "DaoAuthenticationProvider p = new DaoAuthenticationProvider();",
                "DaoAuthenticationProvider p = new DaoAuthenticationProvider(); p.setPasswordEncoder(encoder); p.setUserDetailsService(userDetailsService);",
                "io.elmos.recipes.security.SpringSecurityAuthenticationRecipe",
                "Explicitly wire PasswordEncoder and UserDetailsService on DaoAuthenticationProvider.",
                "Restore implicit wiring.",
                "https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html"
        ));
        register(new ModernizationRule(
                "SEC-020",
                RuleCategory.SECURITY,
                "DelegatingPasswordEncoder BCrypt Upgrades",
                RuleSeverity.MAJOR,
                2,
                "Ensure PasswordEncoderFactories.createDelegatingPasswordEncoder() is used as the standard encoder bean.",
                "return new BCryptPasswordEncoder();",
                "return PasswordEncoderFactories.createDelegatingPasswordEncoder();",
                "io.elmos.recipes.security.SpringSecurityAuthenticationRecipe",
                "Use DelegatingPasswordEncoder for future-proof hash support.",
                "Revert to standalone BCryptPasswordEncoder.",
                "https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html"
        ));
        register(new ModernizationRule(
                "SEC-021",
                RuleCategory.SECURITY,
                "Reactive Security ServerHttpSecurity Lambda Migration",
                RuleSeverity.MAJOR,
                3,
                "Migrate WebFlux ServerHttpSecurity from chained calls to lambda customizers.",
                "http.authorizeExchange().pathMatchers(\"/api/**\").authenticated()",
                "http.authorizeExchange(ex -> ex.pathMatchers(\"/api/**\").authenticated())",
                "io.elmos.worker.security.SpringSecurityFilterChainModernizer",
                "Convert ServerHttpSecurity chained calls to lambda DSL.",
                "Restore chained authorizeExchange.",
                "https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html"
        ));
        register(new ModernizationRule(
                "SEC-022",
                RuleCategory.SECURITY,
                "SecurityContextRepository Delegation Enforcement",
                RuleSeverity.CRITICAL,
                3,
                "Spring Security 6 requires explicit SecurityContextRepository saving when authenticating programmatically.",
                "SecurityContextHolder.getContext().setAuthentication(auth);",
                "securityContextRepository.saveContext(SecurityContextHolder.getContext(), request, response);",
                "io.elmos.worker.security.SpringSecurityFilterChainModernizer",
                "Explicitly invoke securityContextRepository.saveContext after programmatic authentication.",
                "Rely on automatic context persistence (deprecated).",
                "https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html#saving-authentication"
        ));
        register(new ModernizationRule(
                "SEC-023",
                RuleCategory.SECURITY,
                "RequestCache NullRequestCache Stateless Optimization",
                RuleSeverity.MINOR,
                1,
                "Configure NullRequestCache on stateless REST APIs to avoid unnecessary session recreation.",
                "http.requestCache()",
                "http.requestCache(cache -> cache.requestCache(new NullRequestCache()))",
                "io.elmos.worker.security.SpringSecurityFilterChainModernizer",
                "Set NullRequestCache for stateless REST SecurityFilterChain.",
                "Restore default HttpSessionRequestCache.",
                "https://docs.spring.io/spring-security/reference/servlet/architecture.html#request-cache"
        ));
        register(new ModernizationRule(
                "SEC-024",
                RuleCategory.SECURITY,
                "ContentSecurityPolicy Directive Modernization",
                RuleSeverity.MAJOR,
                2,
                "Migrate CSP directives to modern headers(headers -> headers.contentSecurityPolicy(csp -> csp.policyDirectives(...))).",
                "http.headers().contentSecurityPolicy(\"default-src 'self'\")",
                "http.headers(headers -> headers.contentSecurityPolicy(csp -> csp.policyDirectives(\"default-src 'self'\")))",
                "io.elmos.worker.security.SpringSecurityFilterChainModernizer",
                "Convert contentSecurityPolicy to lambda configuration.",
                "Restore chained CSP call.",
                "https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html#headers-csp"
        ));
        register(new ModernizationRule(
                "SEC-025",
                RuleCategory.SECURITY,
                "XssProtection Header Modernization",
                RuleSeverity.INFO,
                1,
                "Refactor xssProtection header configuration to modern lambda block.",
                "http.headers().xssProtection()",
                "http.headers(headers -> headers.xssProtection(Customizer.withDefaults()))",
                "io.elmos.worker.security.SpringSecurityFilterChainModernizer",
                "Use lambda customizer for XSS protection headers.",
                "Restore chained xssProtection call.",
                "https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html#headers-xss"
        ));
        register(new ModernizationRule(
                "SEC-026",
                RuleCategory.SECURITY,
                "UserDetailsService In-Memory to Database Repository",
                RuleSeverity.MAJOR,
                2,
                "Migrate hardcoded inMemoryAuthentication to UserDetailsService implementation.",
                "auth.inMemoryAuthentication().withUser(\"admin\")...",
                "@Bean public UserDetailsService userDetailsService() { return username -> repository.findByUsername(username); }",
                "io.elmos.worker.security.SpringSecurityFilterChainModernizer",
                "Provide dynamic UserDetailsService bean.",
                "Restore in-memory user store.",
                "https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html"
        ));
        register(new ModernizationRule(
                "SEC-027",
                RuleCategory.SECURITY,
                "PermissionEvaluator Domain Object Authorization",
                RuleSeverity.MAJOR,
                3,
                "Declare custom PermissionEvaluator @Bean for domain-level ACL checks.",
                "@Component public class CustomPermissionEvaluator implements PermissionEvaluator",
                "@Bean public MethodSecurityExpressionHandler expressionHandler() { DefaultMethodSecurityExpressionHandler h = new DefaultMethodSecurityExpressionHandler(); h.setPermissionEvaluator(new CustomPermissionEvaluator()); return h; }",
                "io.elmos.worker.security.SpringSecurityFilterChainModernizer",
                "Register PermissionEvaluator with MethodSecurityExpressionHandler.",
                "Restore legacy XML evaluator declaration.",
                "https://docs.spring.io/spring-security/reference/servlet/authorization/expression-based.html"
        ));
        register(new ModernizationRule(
                "SEC-028",
                RuleCategory.SECURITY,
                "OAuth2 Client Registration & Token Exchange",
                RuleSeverity.CRITICAL,
                3,
                "Modernize ClientRegistrationRepository and OAuth2AuthorizedClientManager for Spring Security 6.",
                "http.oauth2Login().and().oauth2Client()",
                "http.oauth2Login(Customizer.withDefaults()).oauth2Client(Customizer.withDefaults())",
                "io.elmos.recipes.security.SpringSecurityOAuth2ResourceServerRecipe",
                "Convert oauth2Login and oauth2Client to lambda DSL.",
                "Restore chained oauth2 client config.",
                "https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html"
        ));
        register(new ModernizationRule(
                "SEC-029",
                RuleCategory.SECURITY,
                "Saml2RelyingParty Registration Modernization",
                RuleSeverity.MAJOR,
                3,
                "Migrate SAML 2.0 relying party login configuration to lambda customizer.",
                "http.saml2Login()",
                "http.saml2Login(Customizer.withDefaults())",
                "io.elmos.worker.security.SpringSecurityFilterChainModernizer",
                "Convert saml2Login chained calls to lambda customizer.",
                "Restore chained saml2 configuration.",
                "https://docs.spring.io/spring-security/reference/servlet/saml2/login/index.html"
        ));
        register(new ModernizationRule(
                "SEC-030",
                RuleCategory.SECURITY,
                "SecurityFilterChain Dual Registration Prevention",
                RuleSeverity.CRITICAL,
                2,
                "Ensure multiple SecurityFilterChain beans have explicit @Order annotations to avoid ambiguous filter precedence.",
                "@Bean public SecurityFilterChain chainOne(HttpSecurity http) ...",
                "@Bean @Order(1) public SecurityFilterChain apiFilterChain(HttpSecurity http) ...\n@Bean @Order(2) public SecurityFilterChain defaultFilterChain(HttpSecurity http) ...",
                "io.elmos.recipes.security.SpringSecurityCustomFilterOrderRecipe",
                "Add @Order annotation to all SecurityFilterChain beans.",
                "Remove @Order annotations.",
                "https://docs.spring.io/spring-security/reference/servlet/configuration/java.html#multiple-httpsecurity"
        ));
    }

    private static void initJpaRules() {
        register(new ModernizationRule(
                "JPA-001",
                RuleCategory.JPA_HIBERNATE,
                "javax.persistence to jakarta.persistence Namespace Migration",
                RuleSeverity.BLOCKER,
                4,
                "Java EE to Jakarta EE migration requires replacing all javax.persistence.* imports with jakarta.persistence.*.",
                "import javax.persistence.*;",
                "import jakarta.persistence.*;",
                "io.elmos.recipes.jpa.Hibernate6TypeMappingRecipe",
                "Replace javax.persistence imports with jakarta.persistence.",
                "Revert imports to javax.persistence.",
                "https://jakarta.ee/specifications/persistence/3.1/"
        ));
        register(new ModernizationRule(
                "JPA-002",
                RuleCategory.JPA_HIBERNATE,
                "Hibernate @TypeDef to @JdbcTypeCode(SqlTypes.JSON)",
                RuleSeverity.BLOCKER,
                3,
                "@TypeDef and @TypeDefs have been removed in Hibernate 6. Use @JdbcTypeCode(SqlTypes.JSON) for JSON and JSONB column mappings.",
                "@Type(type = \"json\")",
                "@JdbcTypeCode(SqlTypes.JSON)",
                "io.elmos.recipes.jpa.Hibernate6TypeMappingRecipe",
                "Replace @Type / @TypeDef with @JdbcTypeCode(SqlTypes.JSON).",
                "Restore Hibernate 5 @TypeDef annotation.",
                "https://docs.jboss.org/hibernate/orm/6.0/userguide/html_single/Hibernate_User_Guide.html#mapping-column-jdbctypecode"
        ));
        register(new ModernizationRule(
                "JPA-003",
                RuleCategory.JPA_HIBERNATE,
                "Legacy Positional Parameter ? to ?1 in JPQL/HQL",
                RuleSeverity.BLOCKER,
                2,
                "Hibernate 6 SQM query engine strictly enforces JPA positional parameter ordinal numbering ?1, ?2 instead of legacy ?.",
                "WHERE u.name = ? AND u.status = ?",
                "WHERE u.name = ?1 AND u.status = ?2",
                "io.elmos.recipes.jpa.SpringDataJpaNamedQueryModernizationRecipe",
                "Number all legacy unindexed positional parameters ? as ?1, ?2, etc.",
                "Revert back to unnumbered question marks.",
                "https://docs.jboss.org/hibernate/orm/6.0/migration-guide/migration-guide.html#query-positional-parameters"
        ));
        register(new ModernizationRule(
                "JPA-004",
                RuleCategory.JPA_HIBERNATE,
                "Deprecated org.hibernate.Criteria to JPA CriteriaBuilder",
                RuleSeverity.BLOCKER,
                4,
                "org.hibernate.Criteria API was removed in Hibernate 6. Queries must be rewritten using JPA CriteriaBuilder or Spring Data Specification.",
                "Criteria criteria = session.createCriteria(Product.class); criteria.add(Restrictions.eq(\"status\", \"ACTIVE\"));",
                "Specification<Product> spec = (root, query, cb) -> cb.equal(root.get(\"status\"), \"ACTIVE\");",
                "io.elmos.recipes.jpa.Hibernate6CriteriaModernizationRecipe",
                "Convert legacy Criteria calls to JPA CriteriaQuery or Spring Data Specifications.",
                "Restore org.hibernate.Criteria under Hibernate 5 compatibility layer.",
                "https://docs.jboss.org/hibernate/orm/6.0/migration-guide/migration-guide.html#legacy-criteria"
        ));
        register(new ModernizationRule(
                "JPA-005",
                RuleCategory.JPA_HIBERNATE,
                "Custom Hibernate Dialect Functions to FunctionContributor SPI",
                RuleSeverity.CRITICAL,
                3,
                "registerFunction() in custom Dialects is removed in Hibernate 6. Use the FunctionContributor SPI to register SQL functions.",
                "public class CustomDialect extends MySQL8Dialect { public CustomDialect() { registerFunction(...); } }",
                "public class CustomFunctionContributor implements FunctionContributor { public void contributeFunctions(FunctionContributions c) { c.getFunctionRegistry().register(...); } }",
                "io.elmos.recipes.jpa.Hibernate6DialectFunctionRecipe",
                "Implement FunctionContributor and register via META-INF/services/org.hibernate.boot.model.FunctionContributor.",
                "Restore custom Dialect subclass with registerFunction.",
                "https://docs.jboss.org/hibernate/orm/6.0/migration-guide/migration-guide.html#function-contributor"
        ));
        register(new ModernizationRule(
                "JPA-006",
                RuleCategory.JPA_HIBERNATE,
                "Hibernate 6 SQM Query Engine Strict Type Alignment",
                RuleSeverity.CRITICAL,
                3,
                "SQM semantic query model verifies operand types strictly in arithmetic, comparisons, and CASE expressions.",
                "SELECT p FROM Product p WHERE p.price > 0",
                "Ensure entity field types match comparison literal types (e.g. BigDecimal.ZERO).",
                "io.elmos.worker.jpa.SpringJpaHibernateQueryModernizer",
                "Align query literal types with entity attribute types.",
                "Disable strict SQM type checking.",
                "https://docs.jboss.org/hibernate/orm/6.0/migration-guide/migration-guide.html#sqm"
        ));
        register(new ModernizationRule(
                "JPA-007",
                RuleCategory.JPA_HIBERNATE,
                "SequenceGenerator Naming and Allocation Size Optimization",
                RuleSeverity.MAJOR,
                2,
                "Hibernate 6 uses modern sequence pooling and strictly aligns sequence names with database schemas.",
                "@SequenceGenerator(name = \"id_seq\", allocationSize = 1)",
                "@SequenceGenerator(name = \"id_seq\", sequenceName = \"id_seq\", allocationSize = 50)",
                "io.elmos.worker.jpa.SpringJpaHibernateQueryModernizer",
                "Ensure sequenceName is explicitly declared and allocationSize is calibrated.",
                "Restore allocationSize = 1.",
                "https://docs.jboss.org/hibernate/orm/6.0/userguide/html_single/Hibernate_User_Guide.html#identifiers-generators-sequence"
        ));
        register(new ModernizationRule(
                "JPA-008",
                RuleCategory.JPA_HIBERNATE,
                "Hibernate Envers @Audited Table Mapping Modernization",
                RuleSeverity.MAJOR,
                3,
                "Hibernate Envers 6.x modernizes revinfo and audit table mappings with instant timestamps and Jakarta persistence annotations.",
                "import org.hibernate.envers.Audited; import javax.persistence.*;",
                "import org.hibernate.envers.Audited; import jakarta.persistence.*;",
                "io.elmos.recipes.jpa.Hibernate6EnversAuditRecipe",
                "Update Envers configuration to Jakarta annotations.",
                "Keep javax Envers mappings.",
                "https://docs.jboss.org/hibernate/orm/6.0/userguide/html_single/Hibernate_User_Guide.html#envers"
        ));
        register(new ModernizationRule(
                "JPA-009",
                RuleCategory.JPA_HIBERNATE,
                "UUID Generator GenericGenerator to @UuidGenerator",
                RuleSeverity.MAJOR,
                2,
                "Hibernate 6 deprecates @GenericGenerator(name=\"uuid2\", strategy=\"uuid2\") in favor of @UuidGenerator.",
                "@GeneratedValue(generator = \"uuid2\") @GenericGenerator(name = \"uuid2\", strategy = \"uuid2\")",
                "@UuidGenerator",
                "io.elmos.recipes.jpa.Hibernate6TypeMappingRecipe",
                "Replace legacy UUID generator declarations with @UuidGenerator.",
                "Restore @GenericGenerator.",
                "https://docs.jboss.org/hibernate/orm/6.0/userguide/html_single/Hibernate_User_Guide.html#identifiers-generators-uuid"
        ));
        register(new ModernizationRule(
                "JPA-010",
                RuleCategory.JPA_HIBERNATE,
                "Composite Primary Key @EmbeddedId / @IdClass Modernization",
                RuleSeverity.MAJOR,
                3,
                "Composite primary keys must implement Serializable, equals(), and hashCode() adhering to JPA 3.1 specification.",
                "public class OrderItemId implements Serializable",
                "Ensure proper equals and hashCode implementation adhering to Jakarta Persistence specifications.",
                "io.elmos.worker.jpa.SpringJpaHibernateQueryModernizer",
                "Verify composite PK classes implement Serializable, equals, hashCode.",
                "Keep legacy unvalidated composite PK.",
                "https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/embeddedid"
        ));
        register(new ModernizationRule(
                "JPA-011",
                RuleCategory.JPA_HIBERNATE,
                "Hibernate Second-Level Cache Region Factory Migration",
                RuleSeverity.MAJOR,
                2,
                "Hibernate 6 requires modern CacheProvider or RegionFactory configured via hibernate.cache.region.factory_class.",
                "hibernate.cache.region.factory_class=org.hibernate.cache.ehcache.EhCacheRegionFactory",
                "hibernate.cache.region.factory_class=org.hibernate.cache.jcache.JCacheRegionFactory",
                "io.elmos.worker.jpa.SpringJpaHibernateQueryModernizer",
                "Migrate second-level cache region factory to JCacheRegionFactory.",
                "Revert to legacy EhCacheRegionFactory.",
                "https://docs.jboss.org/hibernate/orm/6.0/userguide/html_single/Hibernate_User_Guide.html#caching"
        ));
        register(new ModernizationRule(
                "JPA-012",
                RuleCategory.JPA_HIBERNATE,
                "OpenSessionInViewFilter Optimization & Elimination",
                RuleSeverity.MAJOR,
                2,
                "spring.jpa.open-in-view should be set to false in high-throughput microservices to prevent connection pool exhaustion.",
                "spring.jpa.open-in-view=true",
                "spring.jpa.open-in-view=false",
                "io.elmos.worker.jpa.SpringJpaHibernateQueryModernizer",
                "Disable OSIV and fetch required associations eagerly via EntityGraph or join fetch.",
                "Enable open-in-view=true.",
                "https://docs.spring.io/spring-boot/docs/current/reference/html/data.html#data.sql.jpa-and-spring-data.open-entity-manager-in-view"
        ));
        register(new ModernizationRule(
                "JPA-013",
                RuleCategory.JPA_HIBERNATE,
                "TransactionManagement Spring @Transactional Modernization",
                RuleSeverity.CRITICAL,
                2,
                "Replace javax.transaction.Transactional with org.springframework.transaction.annotation.Transactional or jakarta.transaction.Transactional.",
                "import javax.transaction.Transactional;",
                "import org.springframework.transaction.annotation.Transactional;",
                "io.elmos.worker.jpa.SpringJpaHibernateQueryModernizer",
                "Update @Transactional imports to Spring Transactional annotation.",
                "Revert to javax.transaction.Transactional.",
                "https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html"
        ));
        register(new ModernizationRule(
                "JPA-014",
                RuleCategory.JPA_HIBERNATE,
                "Spring Data JPA CrudRepository / JpaRepository API Updates",
                RuleSeverity.MAJOR,
                2,
                "Spring Data JPA 3.x / Boot 3.x eliminates getOne(ID) in favor of getReferenceById(ID) and findById(ID).",
                "repository.getOne(id);",
                "repository.getReferenceById(id);",
                "io.elmos.worker.jpa.SpringJpaHibernateQueryModernizer",
                "Replace getOne(ID) with getReferenceById(ID).",
                "Restore getOne(ID).",
                "https://docs.spring.io/spring-data/jpa/reference/jpa/repository-query-keywords.html"
        ));
        register(new ModernizationRule(
                "JPA-015",
                RuleCategory.JPA_HIBERNATE,
                "Derived Query Method Keywords & Specifiers",
                RuleSeverity.MINOR,
                2,
                "Align derived query methods with Spring Data 3.x keyword standards, eliminating deprecated findBy[Property]IsNull in favor of IsNull.",
                "findByNameIsNotNull(String name)",
                "findByNameNotNull()",
                "io.elmos.worker.jpa.SpringJpaHibernateQueryModernizer",
                "Normalize derived query method names according to Spring Data JPA 3.x grammar.",
                "Restore non-standard derived query method names.",
                "https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html"
        ));
        register(new ModernizationRule(
                "JPA-016",
                RuleCategory.JPA_HIBERNATE,
                "EntityGraph Dynamic Fetch Plan Specification",
                RuleSeverity.MAJOR,
                3,
                "Use @EntityGraph to solve N+1 queries cleanly without brittle Hibernate FetchMode.JOIN.",
                "@Fetch(FetchMode.JOIN) private Set<Item> items;",
                "@EntityGraph(attributePaths = {\"items\"}) List<Order> findAll();",
                "io.elmos.worker.jpa.SpringJpaHibernateQueryModernizer",
                "Migrate legacy @Fetch annotations to Spring Data @EntityGraph on repository query methods.",
                "Restore @Fetch(FetchMode.JOIN).",
                "https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html#jpa.entity-graph"
        ));
        register(new ModernizationRule(
                "JPA-017",
                RuleCategory.JPA_HIBERNATE,
                "Projection Interface and DTO Record Constructor Mapping",
                RuleSeverity.MAJOR,
                2,
                "Migrate JPA custom result DTOs to Java 21 Records with JPQL constructor expressions.",
                "SELECT new io.elmos.dto.ProductSummary(p.id, p.title) FROM Product p",
                "public record ProductSummary(Long id, String title) {}",
                "io.elmos.worker.jpa.SpringJpaHibernateQueryModernizer",
                "Modernize DTO classes to Java 21 records and use JPQL constructor queries.",
                "Restore legacy JavaBeans with getters/setters.",
                "https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html"
        ));
        register(new ModernizationRule(
                "JPA-018",
                RuleCategory.JPA_HIBERNATE,
                "CascadeType and OrphanRemoval State Management",
                RuleSeverity.MAJOR,
                2,
                "Ensure CascadeType.ALL with orphanRemoval=true is used appropriately on parent-child collection mappings.",
                "@OneToMany(cascade = CascadeType.ALL, orphanRemoval = true)",
                "Verify parent-child bidirectional link methods (addItem, removeItem) manage both sides.",
                "io.elmos.worker.jpa.SpringJpaHibernateQueryModernizer",
                "Add synchronization helper methods to entities with orphanRemoval=true.",
                "Remove bidirectional synchronization helpers.",
                "https://docs.jboss.org/hibernate/orm/6.0/userguide/html_single/Hibernate_User_Guide.html#associations-orphanRemoval"
        ));
        register(new ModernizationRule(
                "JPA-019",
                RuleCategory.JPA_HIBERNATE,
                "AuditingEntityListener Date/Time java.time Migration",
                RuleSeverity.MAJOR,
                2,
                "Migrate legacy java.util.Date / java.sql.Timestamp @CreatedDate and @LastModifiedDate fields to java.time.Instant or LocalDateTime.",
                "@CreatedDate private java.util.Date createdAt;",
                "@CreatedDate private java.time.Instant createdAt;",
                "io.elmos.worker.jpa.SpringJpaHibernateQueryModernizer",
                "Convert audit timestamp fields to java.time.Instant.",
                "Restore java.util.Date audit fields.",
                "https://docs.spring.io/spring-data/jpa/reference/auditing.html"
        ));
        register(new ModernizationRule(
                "JPA-020",
                RuleCategory.JPA_HIBERNATE,
                "Batch Insert / Update JDBC Batch Size Configuration",
                RuleSeverity.MAJOR,
                2,
                "Configure spring.jpa.properties.hibernate.jdbc.batch_size=50 and order_inserts/order_updates for high throughput.",
                "spring.jpa.properties.hibernate.jdbc.batch_size=50\nspring.jpa.properties.hibernate.order_inserts=true",
                "Enable JDBC batch size and ordering properties.",
                "io.elmos.worker.jpa.SpringJpaHibernateQueryModernizer",
                "Set batch_size and order_inserts/updates in application properties.",
                "Remove batching properties.",
                "https://docs.jboss.org/hibernate/orm/6.0/userguide/html_single/Hibernate_User_Guide.html#batch"
        ));
        register(new ModernizationRule(
                "JPA-021",
                RuleCategory.JPA_HIBERNATE,
                "Optimistic Locking @Version Field Types",
                RuleSeverity.CRITICAL,
                2,
                "Ensure @Version fields use Long or Integer instead of timestamp types for reliable lock checking.",
                "@Version private Long version;",
                "Use numeric version field for deterministic optimistic locking.",
                "io.elmos.worker.jpa.SpringJpaHibernateQueryModernizer",
                "Verify @Version field uses Long or Integer.",
                "Restore timestamp based version.",
                "https://docs.jboss.org/hibernate/orm/6.0/userguide/html_single/Hibernate_User_Guide.html#locking-optimistic"
        ));
        register(new ModernizationRule(
                "JPA-022",
                RuleCategory.JPA_HIBERNATE,
                "Pessimistic Locking LockModeType Query Hints",
                RuleSeverity.MAJOR,
                2,
                "Explicitly configure LockModeType.PESSIMISTIC_WRITE with javax.persistence.lock.timeout hint.",
                "@Lock(LockModeType.PESSIMISTIC_WRITE)\n@QueryHints(@QueryHint(name = \"jakarta.persistence.lock.timeout\", value = \"5000\"))",
                "Set lock timeout on pessimistic queries to prevent database deadlocks.",
                "io.elmos.worker.jpa.SpringJpaHibernateQueryModernizer",
                "Add lock timeout query hint to pessimistic lock queries.",
                "Remove lock timeout hint.",
                "https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html#jpa.query-hints"
        ));
        register(new ModernizationRule(
                "JPA-023",
                RuleCategory.JPA_HIBERNATE,
                "Dialect Auto-Detection and Removal of Explicit Dialect Class",
                RuleSeverity.MAJOR,
                2,
                "Remove explicit spring.jpa.database-platform or hibernate.dialect declarations; allow Hibernate 6 to detect the dialect automatically from JDBC metadata.",
                "spring.jpa.properties.hibernate.dialect=org.hibernate.dialect.MySQL57Dialect",
                "// Remove explicit dialect property; Hibernate 6 detects automatically.",
                "io.elmos.worker.jpa.SpringJpaHibernateQueryModernizer",
                "Remove obsolete dialect properties from configuration files.",
                "Restore explicit dialect.",
                "https://docs.jboss.org/hibernate/orm/6.0/migration-guide/migration-guide.html#dialect-resolution"
        ));
        register(new ModernizationRule(
                "JPA-024",
                RuleCategory.JPA_HIBERNATE,
                "N+1 Query Elimination through Join Fetch / Subselect",
                RuleSeverity.CRITICAL,
                3,
                "Identify and eliminate N+1 select queries by refactoring lazy collections with join fetch or @Fetch(FetchMode.SUBSELECT).",
                "@Query(\"SELECT o FROM Order o JOIN FETCH o.orderItems WHERE o.status = ?1\")",
                "Use join fetch to eagerly load associations in a single SQL query.",
                "io.elmos.worker.jpa.SpringJpaHibernateQueryModernizer",
                "Refactor repository query methods to use join fetch.",
                "Restore lazy collection queries.",
                "https://docs.jboss.org/hibernate/orm/6.0/userguide/html_single/Hibernate_User_Guide.html#fetching-join-fetch"
        ));
        register(new ModernizationRule(
                "JPA-025",
                RuleCategory.JPA_HIBERNATE,
                "Spatial Geometry Types Hibernate-Spatial 6.x Migration",
                RuleSeverity.MAJOR,
                3,
                "Migrate legacy spatial geometry types to Hibernate 6 native spatial support and JTS 1.19+.",
                "import org.hibernate.spatial.JTSGeometryJavaType;",
                "import org.locationtech.jts.geom.Point;",
                "io.elmos.worker.jpa.SpringJpaHibernateQueryModernizer",
                "Update spatial imports and types to JTS LocationTech standards.",
                "Restore legacy Vividsolutions spatial types.",
                "https://docs.jboss.org/hibernate/orm/6.0/userguide/html_single/Hibernate_User_Guide.html#spatial"
        ));
        register(new ModernizationRule(
                "JPA-026",
                RuleCategory.JPA_HIBERNATE,
                "AttributeConverter AutoApply Lifecycle Enforcement",
                RuleSeverity.MAJOR,
                2,
                "Ensure @Converter(autoApply = true) implementations handle null values safely without NullPointerException.",
                "@Converter(autoApply = true) public class MonetaryAmountConverter implements AttributeConverter<MonetaryAmount, BigDecimal>",
                "Add null checks: if (attribute == null) return null;",
                "io.elmos.worker.jpa.SpringJpaHibernateQueryModernizer",
                "Add defensive null guards to AttributeConverter methods.",
                "Remove null guards.",
                "https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/attributeconverter"
        ));
        register(new ModernizationRule(
                "JPA-027",
                RuleCategory.JPA_HIBERNATE,
                "Multitenancy ConnectionProvider & CurrentTenantIdentifier",
                RuleSeverity.CRITICAL,
                4,
                "Hibernate 6 modernizes multitenancy via TenantResolver and MultiTenantConnectionProvider implementations.",
                "class CustomMultiTenantConnectionProvider implements MultiTenantConnectionProvider",
                "Implement modern MultiTenantConnectionProvider with Jakarta Persistence 3.x.",
                "io.elmos.worker.jpa.SpringJpaHibernateQueryModernizer",
                "Update multi-tenancy provider signatures for Hibernate 6.",
                "Keep Hibernate 5 multi-tenancy interfaces.",
                "https://docs.jboss.org/hibernate/orm/6.0/userguide/html_single/Hibernate_User_Guide.html#multitenacy"
        ));
        register(new ModernizationRule(
                "JPA-028",
                RuleCategory.JPA_HIBERNATE,
                "Native Query Parameter Binding Modernization",
                RuleSeverity.MAJOR,
                2,
                "Native SQL queries in Hibernate 6 must use named parameters (:param) or numbered positional parameters (?1).",
                "@Query(value = \"SELECT * FROM users WHERE status = ?\", nativeQuery = true)",
                "@Query(value = \"SELECT * FROM users WHERE status = ?1\", nativeQuery = true)",
                "io.elmos.recipes.jpa.SpringDataJpaNamedQueryModernizationRecipe",
                "Update positional parameters in native SQL queries to indexed numbers (?1).",
                "Restore unnumbered ? parameters.",
                "https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html#jpa.query.native"
        ));
        register(new ModernizationRule(
                "JPA-029",
                RuleCategory.JPA_HIBERNATE,
                "StoredProcedureQuery RefCursor Parameter Registration",
                RuleSeverity.MAJOR,
                3,
                "Register REF_CURSOR output parameters on StoredProcedureQuery adhering to Jakarta Persistence 3.1.",
                "query.registerStoredProcedureParameter(1, Class.class, ParameterMode.REF_CURSOR);",
                "query.registerStoredProcedureParameter(1, void.class, ParameterMode.REF_CURSOR);",
                "io.elmos.worker.jpa.SpringJpaHibernateQueryModernizer",
                "Use void.class when registering REF_CURSOR output parameter in Hibernate 6.",
                "Restore Class.class for ref cursor.",
                "https://docs.jboss.org/hibernate/orm/6.0/userguide/html_single/Hibernate_User_Guide.html#sp-ref-cursor"
        ));
        register(new ModernizationRule(
                "JPA-030",
                RuleCategory.JPA_HIBERNATE,
                "EntityManagerFactory / DataSource Pool Connection Tuning",
                RuleSeverity.CRITICAL,
                3,
                "Configure HikariCP maximumPoolSize, minimumIdle, idleTimeout, and maxLifetime for Spring Boot 3/4 defaults.",
                "spring.datasource.hikari.maximum-pool-size=20\nspring.datasource.hikari.minimum-idle=5",
                "Tune HikariCP parameters for enterprise database workloads.",
                "io.elmos.worker.jpa.SpringJpaHibernateQueryModernizer",
                "Apply recommended HikariCP connection pool settings in application.yml.",
                "Revert to default unconfigured pool settings.",
                "https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby"
        ));
    }

    private static void initCloudRules() {
        register(new ModernizationRule(
                "CLD-001",
                RuleCategory.SPRING_CLOUD,
                "Netflix Ribbon to Spring Cloud LoadBalancer Migration",
                RuleSeverity.BLOCKER,
                4,
                "Netflix Ribbon has been removed. Replace spring-cloud-starter-netflix-ribbon with spring-cloud-starter-loadbalancer and @RibbonClient with @LoadBalancerClient.",
                "@RibbonClient(name = \"inventory-service\")",
                "@LoadBalancerClient(name = \"inventory-service\")",
                "io.elmos.recipes.cloud.SpringCloudRibbonToLoadBalancerRecipe",
                "Replace Ribbon dependency and annotations with Spring Cloud LoadBalancer.",
                "Restore Ribbon dependencies.",
                "https://docs.spring.io/spring-cloud-commons/docs/current/reference/html/#spring-cloud-loadbalancer"
        ));
        register(new ModernizationRule(
                "CLD-002",
                RuleCategory.SPRING_CLOUD,
                "Netflix Zuul to Spring Cloud Gateway GlobalFilter Migration",
                RuleSeverity.BLOCKER,
                5,
                "Netflix Zuul 1.x is completely removed. Replace with Spring Cloud Gateway reactive RouteLocator and GlobalFilter architecture.",
                "@EnableZuulProxy public class GatewayApplication",
                "@SpringBootApplication public class GatewayApplication { @Bean public RouteLocator customRouteLocator(RouteLocatorBuilder builder) { ... } }",
                "io.elmos.recipes.cloud.SpringCloudZuulToGatewayRecipe",
                "Migrate Zuul routes and filters to Spring Cloud Gateway RouteLocator and GlobalFilter.",
                "Revert to Zuul proxy under Spring Cloud Netflix.",
                "https://docs.spring.io/spring-cloud-gateway/docs/current/reference/html/"
        ));
        register(new ModernizationRule(
                "CLD-003",
                RuleCategory.SPRING_CLOUD,
                "Netflix Hystrix to Resilience4j CircuitBreaker Migration",
                RuleSeverity.BLOCKER,
                4,
                "Netflix Hystrix has been removed. Replace @HystrixCommand with Resilience4j @CircuitBreaker(name = \"...\", fallbackMethod = \"...\").",
                "@HystrixCommand(fallbackMethod = \"fallback\")",
                "@CircuitBreaker(name = \"orderService\", fallbackMethod = \"fallback\")",
                "io.elmos.recipes.cloud.SpringCloudHystrixToResilience4jRecipe",
                "Replace Hystrix dependency and annotations with io.github.resilience4j:resilience4j-spring-boot3.",
                "Restore Hystrix annotations.",
                "https://resilience4j.readme.io/docs/circuitbreaker"
        ));
        register(new ModernizationRule(
                "CLD-004",
                RuleCategory.SPRING_CLOUD,
                "OpenFeign Package Namespace org.springframework.cloud.openfeign",
                RuleSeverity.BLOCKER,
                2,
                "Update Feign client imports from legacy org.springframework.cloud.netflix.feign to org.springframework.cloud.openfeign.",
                "import org.springframework.cloud.netflix.feign.FeignClient;",
                "import org.springframework.cloud.openfeign.FeignClient;",
                "io.elmos.recipes.cloud.SpringCloudOpenFeignModernizationRecipe",
                "Replace legacy Feign import package with org.springframework.cloud.openfeign.",
                "Restore netflix.feign package import.",
                "https://docs.spring.io/spring-cloud-openfeign/docs/current/reference/html/"
        ));
        register(new ModernizationRule(
                "CLD-005",
                RuleCategory.SPRING_CLOUD,
                "Eureka Client Configuration and Multi-Zone Discovery",
                RuleSeverity.MAJOR,
                3,
                "Update Eureka Client configuration for Spring Cloud 2024.x, removing deprecated jersey 1 client dependencies.",
                "eureka.client.serviceUrl.defaultZone=http://localhost:8761/eureka/",
                "eureka.client.service-url.defaultZone=http://localhost:8761/eureka/",
                "io.elmos.recipes.cloud.SpringCloudEurekaDiscoveryRecipe",
                "Migrate Eureka client properties to kebab-case format.",
                "Restore camelCase Eureka properties.",
                "https://docs.spring.io/spring-cloud-netflix/docs/current/reference/html/#service-discovery-eureka-clients"
        ));
        register(new ModernizationRule(
                "CLD-006",
                RuleCategory.SPRING_CLOUD,
                "bootstrap.yml to spring.config.import Config Server Migration",
                RuleSeverity.BLOCKER,
                3,
                "Spring Cloud no longer reads bootstrap.yml by default. Migrate Config Server connections to spring.config.import=optional:configserver: in application.yml.",
                "# in bootstrap.yml\nspring.cloud.config.uri=http://localhost:8888",
                "# in application.yml\nspring.config.import=optional:configserver:http://localhost:8888",
                "io.elmos.recipes.cloud.SpringCloudConfigBootstrapRecipe",
                "Migrate properties from bootstrap.yml to application.yml with spring.config.import.",
                "Add spring-cloud-starter-bootstrap to preserve legacy behavior.",
                "https://docs.spring.io/spring-cloud-commons/docs/current/reference/html/#config-data-migration"
        ));
        register(new ModernizationRule(
                "CLD-007",
                RuleCategory.SPRING_CLOUD,
                "Spring Cloud Sleuth to Micrometer Tracing & OpenTelemetry",
                RuleSeverity.BLOCKER,
                3,
                "Spring Cloud Sleuth is replaced in Boot 3/4 by Micrometer Tracing with Brave or OpenTelemetry bridge.",
                "<artifactId>spring-cloud-starter-sleuth</artifactId>",
                "<artifactId>micrometer-tracing-bridge-otel</artifactId>\n<artifactId>opentelemetry-exporter-otlp</artifactId>",
                "io.elmos.recipes.cloud.SpringCloudDistributedTracingRecipe",
                "Replace Sleuth with micrometer-tracing-bridge-otel and exporter.",
                "Restore spring-cloud-starter-sleuth.",
                "https://micrometer.io/docs/tracing"
        ));
        register(new ModernizationRule(
                "CLD-008",
                RuleCategory.SPRING_CLOUD,
                "Archaius Dynamic Configuration Replacement with Spring Boot Config",
                RuleSeverity.MAJOR,
                2,
                "Netflix Archaius is removed. Use Spring Boot @ConfigurationProperties with @RefreshScope.",
                "DynamicPropertyFactory.getInstance().getStringProperty(\"key\", \"default\");",
                "@ConfigurationProperties(prefix = \"app\")\npublic class AppConfig { ... }",
                "io.elmos.worker.cloud.SpringCloudMicroservicesModernizer",
                "Replace Archaius dynamic properties with typed Spring @ConfigurationProperties.",
                "Restore Archaius library.",
                "https://docs.spring.io/spring-boot/docs/current/reference/html/features.html#features.external-config.typesafe-configuration-properties"
        ));
        register(new ModernizationRule(
                "CLD-009",
                RuleCategory.SPRING_CLOUD,
                "Config Client Fail-Fast and Retry Interceptor Configuration",
                RuleSeverity.MAJOR,
                2,
                "Configure fail-fast and retry for Spring Config Client using spring.cloud.config.fail-fast=true with spring-retry.",
                "spring.cloud.config.fail-fast=true",
                "Enable fail-fast and configure retry max attempts in application.yml.",
                "io.elmos.worker.cloud.SpringCloudMicroservicesModernizer",
                "Add fail-fast property and spring-retry dependency.",
                "Remove fail-fast configuration.",
                "https://docs.spring.io/spring-cloud-config/docs/current/reference/html/#config-client-fail-fast"
        ));
        register(new ModernizationRule(
                "CLD-010",
                RuleCategory.SPRING_CLOUD,
                "Spring Cloud Bus Kafka / RabbitMQ Event Distribution",
                RuleSeverity.MAJOR,
                3,
                "Modernize Spring Cloud Bus refresh event messaging to use spring-cloud-bus with modern Kafka/Rabbit binder.",
                "<artifactId>spring-cloud-starter-bus-amqp</artifactId>",
                "<artifactId>spring-cloud-starter-bus-amqp</artifactId> <!-- with Spring 6 AMQP -->",
                "io.elmos.worker.cloud.SpringCloudMicroservicesModernizer",
                "Upgrade Spring Cloud Bus dependencies to 2024.x release train.",
                "Restore legacy Cloud Bus dependencies.",
                "https://docs.spring.io/spring-cloud-bus/docs/current/reference/html/"
        ));
        register(new ModernizationRule(
                "CLD-011",
                RuleCategory.SPRING_CLOUD,
                "Gateway RateLimiter Redis Token Bucket Filter",
                RuleSeverity.CRITICAL,
                3,
                "Configure RequestRateLimiter gateway filter with RedisRateLimiter and KeyResolver bean.",
                "@Bean public KeyResolver userKeyResolver() { return exchange -> Mono.just(exchange.getRequest().getRemoteAddress().getAddress().getHostAddress()); }",
                "Declare KeyResolver @Bean and configure redis-rate-limiter.replenishRate in application.yml.",
                "io.elmos.worker.cloud.SpringCloudMicroservicesModernizer",
                "Register KeyResolver bean and configure route filters in Gateway.",
                "Remove rate limiting filters.",
                "https://docs.spring.io/spring-cloud-gateway/docs/current/reference/html/#the-requestratelimiter-gatewayfilter-factory"
        ));
        register(new ModernizationRule(
                "CLD-012",
                RuleCategory.SPRING_CLOUD,
                "Resilience4j Retry Configuration and Exponential Backoff",
                RuleSeverity.MAJOR,
                2,
                "Configure Resilience4j @Retry with exponential backoff and maxAttempts in application.yml.",
                "resilience4j.retry.instances.default.maxAttempts=3\nresilience4j.retry.instances.default.waitDuration=500ms",
                "Add Resilience4j retry configuration block.",
                "io.elmos.recipes.cloud.SpringCloudHystrixToResilience4jRecipe",
                "Configure retry parameters in application.yml.",
                "Remove retry configuration.",
                "https://resilience4j.readme.io/docs/retry"
        ));
        register(new ModernizationRule(
                "CLD-013",
                RuleCategory.SPRING_CLOUD,
                "Resilience4j RateLimiter and Bulkhead Isolation",
                RuleSeverity.MAJOR,
                3,
                "Configure ThreadPoolBulkhead and RateLimiter annotations to isolate critical microservice thread pools.",
                "@Bulkhead(name = \"orderBulkhead\", type = Bulkhead.Type.THREADPOOL)",
                "Annotate remote service callers with @Bulkhead for thread pool isolation.",
                "io.elmos.recipes.cloud.SpringCloudHystrixToResilience4jRecipe",
                "Add @Bulkhead and configure bulkhead thread pool sizes.",
                "Remove bulkhead isolation.",
                "https://resilience4j.readme.io/docs/bulkhead"
        ));
        register(new ModernizationRule(
                "CLD-014",
                RuleCategory.SPRING_CLOUD,
                "OpenFeign ErrorDecoder Custom Business Exception Mapping",
                RuleSeverity.MAJOR,
                2,
                "Implement ErrorDecoder to translate remote HTTP 4xx/5xx status codes into typed domain exceptions.",
                "public class CustomFeignErrorDecoder implements ErrorDecoder",
                "@Bean public ErrorDecoder errorDecoder() { return new CustomFeignErrorDecoder(); }",
                "io.elmos.recipes.cloud.SpringCloudOpenFeignModernizationRecipe",
                "Provide custom ErrorDecoder bean in FeignClient configuration.",
                "Use default FeignException handling.",
                "https://docs.spring.io/spring-cloud-openfeign/docs/current/reference/html/#spring-cloud-feign-overriding-defaults"
        ));
        register(new ModernizationRule(
                "CLD-015",
                RuleCategory.SPRING_CLOUD,
                "OpenFeign RequestInterceptor Distributed Header Propagation",
                RuleSeverity.MAJOR,
                2,
                "Register RequestInterceptor @Bean to propagate Authorization and Tenant-ID headers across Feign calls.",
                "@Bean public RequestInterceptor authRequestInterceptor() { return template -> template.header(\"Authorization\", token); }",
                "Add RequestInterceptor to forward security and tracing headers.",
                "io.elmos.recipes.cloud.SpringCloudOpenFeignModernizationRecipe",
                "Declare RequestInterceptor bean for header forwarding.",
                "Remove header interceptor.",
                "https://docs.spring.io/spring-cloud-openfeign/docs/current/reference/html/#feign-requestinterceptor"
        ));
        register(new ModernizationRule(
                "CLD-016",
                RuleCategory.SPRING_CLOUD,
                "Consumed Service HealthCheckHandler Registration",
                RuleSeverity.MINOR,
                2,
                "Register Eureka HealthCheckHandler to synchronize Eureka instance status with Spring Boot Actuator health.",
                "eureka.client.healthcheck.enabled=true",
                "Enable Eureka healthcheck in application.yml.",
                "io.elmos.worker.cloud.SpringCloudMicroservicesModernizer",
                "Set eureka.client.healthcheck.enabled=true.",
                "Disable Eureka health check synchronization.",
                "https://docs.spring.io/spring-cloud-netflix/docs/current/reference/html/#status-page-and-health-indicator"
        ));
        register(new ModernizationRule(
                "CLD-017",
                RuleCategory.SPRING_CLOUD,
                "Spring Cloud Kubernetes Discovery & ConfigMap Migration",
                RuleSeverity.CRITICAL,
                4,
                "Migrate from Netflix Eureka to Kubernetes-native service discovery and ConfigMap property sources.",
                "<artifactId>spring-cloud-starter-kubernetes-client-all</artifactId>",
                "Configure Spring Cloud Kubernetes discovery and reload controllers.",
                "io.elmos.worker.cloud.SpringCloudMicroservicesModernizer",
                "Add spring-cloud-starter-kubernetes-fabric8 or client dependencies.",
                "Keep Eureka discovery client.",
                "https://docs.spring.io/spring-cloud-kubernetes/docs/current/reference/html/"
        ));
        register(new ModernizationRule(
                "CLD-018",
                RuleCategory.SPRING_CLOUD,
                "Spring Cloud Stream Functional Programming Model",
                RuleSeverity.CRITICAL,
                4,
                "Migrate legacy @EnableBinding(Sink.class/Source.class) to Java functional java.util.function.Consumer / Function / Supplier @Beans.",
                "@EnableBinding(Processor.class) public class MessageListener",
                "@Bean public Function<OrderEvent, OrderNotification> processOrder() { return event -> ...; }",
                "io.elmos.worker.cloud.SpringCloudMicroservicesModernizer",
                "Replace @EnableBinding with functional @Bean declarations.",
                "Restore @EnableBinding legacy model.",
                "https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/#_functional_binding"
        ));
        register(new ModernizationRule(
                "CLD-019",
                RuleCategory.SPRING_CLOUD,
                "Cloud Task & Batch Scheduling Modernization",
                RuleSeverity.MAJOR,
                3,
                "Update Spring Cloud Task and Spring Batch 5.x integration, using @EnableTask and modern JobRepository.",
                "@EnableTask public class BatchTaskApplication",
                "Ensure Batch 5.x DefaultBatchConfiguration is used alongside Cloud Task.",
                "io.elmos.worker.cloud.SpringCloudMicroservicesModernizer",
                "Update Batch and Task configuration for Boot 3/4.",
                "Restore Spring Batch 4.x configuration.",
                "https://docs.spring.io/spring-cloud-task/docs/current/reference/html/"
        ));
        register(new ModernizationRule(
                "CLD-020",
                RuleCategory.SPRING_CLOUD,
                "Distributed Locking Spring Integration Redis/JDBC Lock",
                RuleSeverity.MAJOR,
                3,
                "Use Spring Integration RedisLockRegistry or JdbcLockRegistry for distributed mutex synchronization.",
                "@Bean public LockRegistry lockRegistry(RedisConnectionFactory factory) { return new RedisLockRegistry(factory, \"distributed-lock\"); }",
                "Declare LockRegistry @Bean and obtain Lock instances.",
                "io.elmos.worker.cloud.SpringCloudMicroservicesModernizer",
                "Provide LockRegistry bean for distributed locking.",
                "Use uncoordinated local locks.",
                "https://docs.spring.io/spring-integration/reference/redis.html#redis-lock-registry"
        ));
        register(new ModernizationRule(
                "CLD-021",
                RuleCategory.SPRING_CLOUD,
                "Service Mesh Sidecar mTLS Header Preservation",
                RuleSeverity.MAJOR,
                2,
                "Configure Istio/Linkerd header propagation (x-request-id, x-b3-traceid, x-b3-spanid) across outbound calls.",
                "Preserve incoming tracing headers on outgoing RestClient / Feign calls.",
                "Configure WebClient/RestClient exchange filter function.",
                "io.elmos.worker.cloud.SpringCloudMicroservicesModernizer",
                "Add tracing header propagation filter.",
                "Remove header propagation filter.",
                "https://istio.io/latest/docs/tasks/observability/distributed-tracing/overview/"
        ));
        register(new ModernizationRule(
                "CLD-022",
                RuleCategory.SPRING_CLOUD,
                "Spring Cloud Contract CDC Consumer-Driven Contract Verification",
                RuleSeverity.MAJOR,
                3,
                "Modernize Spring Cloud Contract DSL definitions and stub runner dependencies for Spring 6 / JUnit 5.",
                "org.springframework.cloud.contract.spec.Contract.make { ... }",
                "Update contracts to Groovy or YAML DSL and use modern Stub Runner.",
                "io.elmos.worker.cloud.SpringCloudMicroservicesModernizer",
                "Update Spring Cloud Contract maven plugin and test dependencies.",
                "Keep legacy Contract versions.",
                "https://docs.spring.io/spring-cloud-contract/docs/current/reference/html/"
        ));
        register(new ModernizationRule(
                "CLD-023",
                RuleCategory.SPRING_CLOUD,
                "OpenFeign Client Apache HttpClient 5 / OkHttp Tuning",
                RuleSeverity.MAJOR,
                2,
                "Configure feign.okhttp.enabled=true or feign.httpclient.hc5.enabled=true for connection pooling.",
                "spring.cloud.openfeign.httpclient.hc5.enabled=true",
                "Enable HC5 client in application properties.",
                "io.elmos.recipes.cloud.SpringCloudOpenFeignModernizationRecipe",
                "Set spring.cloud.openfeign.httpclient.hc5.enabled=true.",
                "Use default Java URLConnection.",
                "https://docs.spring.io/spring-cloud-openfeign/docs/current/reference/html/#httpclient-support"
        ));
        register(new ModernizationRule(
                "CLD-024",
                RuleCategory.SPRING_CLOUD,
                "Spring Cloud Gateway RouteLocator Custom Predicate Factory",
                RuleSeverity.MAJOR,
                3,
                "Implement AbstractRoutePredicateFactory for domain-specific route matching logic in Spring Cloud Gateway.",
                "public class CustomHeaderRoutePredicateFactory extends AbstractRoutePredicateFactory<Config>",
                "Register custom predicate factory as @Component.",
                "io.elmos.recipes.cloud.SpringCloudZuulToGatewayRecipe",
                "Provide custom RoutePredicateFactory component.",
                "Remove custom predicate.",
                "https://docs.spring.io/spring-cloud-gateway/docs/current/reference/html/#writing-custom-route-predicate-factories"
        ));
        register(new ModernizationRule(
                "CLD-025",
                RuleCategory.SPRING_CLOUD,
                "Gateway WebFilter CORS and Preflight Request Handling",
                RuleSeverity.MAJOR,
                2,
                "Configure global CORS on Spring Cloud Gateway via spring.cloud.gateway.globalcors in application.yml.",
                "spring.cloud.gateway.globalcors.cors-configurations.\"[/**]\".allowedOrigins=\"*\"",
                "Add global CORS configuration to Gateway application.yml.",
                "io.elmos.recipes.cloud.SpringCloudZuulToGatewayRecipe",
                "Set gateway globalcors properties.",
                "Remove gateway CORS properties.",
                "https://docs.spring.io/spring-cloud-gateway/docs/current/reference/html/#cors-configuration"
        ));
        register(new ModernizationRule(
                "CLD-026",
                RuleCategory.SPRING_CLOUD,
                "Eureka Server Peer Replication Network Tuning",
                RuleSeverity.MAJOR,
                2,
                "Configure Eureka server peer node replication timeout and retry parameters for high availability.",
                "eureka.server.peerNodeConnectTimeoutMs=2000\neureka.server.peerNodeReadTimeoutMs=2000",
                "Tune Eureka server peer communication timeouts.",
                "io.elmos.recipes.cloud.SpringCloudEurekaDiscoveryRecipe",
                "Configure peer node connection settings in eureka server yml.",
                "Restore default timeouts.",
                "https://docs.spring.io/spring-cloud-netflix/docs/current/reference/html/#spring-cloud-eureka-server"
        ));
        register(new ModernizationRule(
                "CLD-027",
                RuleCategory.SPRING_CLOUD,
                "Vault Secret Integration with spring.config.import",
                RuleSeverity.CRITICAL,
                3,
                "Integrate HashiCorp Vault via spring.config.import=vault:// for dynamic secrets in Spring Boot 3/4.",
                "spring.config.import=vault://secret/my-application",
                "Add vault config import property in application.yml.",
                "io.elmos.worker.cloud.SpringCloudMicroservicesModernizer",
                "Configure Vault import uri and authentication token in application properties.",
                "Remove vault import.",
                "https://docs.spring.io/spring-cloud-vault/docs/current/reference/html/#vault.config-data"
        ));
        register(new ModernizationRule(
                "CLD-028",
                RuleCategory.SPRING_CLOUD,
                "Actuator RefreshScope Configuration Dynamic Reloading",
                RuleSeverity.MAJOR,
                2,
                "Annotate dynamic beans with @RefreshScope and expose POST /actuator/refresh for runtime property updates.",
                "@RefreshScope @Component public class DynamicFeatureConfig",
                "management.endpoints.web.exposure.include=health,info,refresh",
                "io.elmos.worker.cloud.SpringCloudMicroservicesModernizer",
                "Add @RefreshScope to configurable components and expose refresh endpoint.",
                "Remove @RefreshScope.",
                "https://docs.spring.io/spring-cloud-commons/docs/current/reference/html/#refresh-scope"
        ));
        register(new ModernizationRule(
                "CLD-029",
                RuleCategory.SPRING_CLOUD,
                "Distributed Context MDC Trace ID Propagation",
                RuleSeverity.MAJOR,
                2,
                "Configure Logback / SLF4J pattern to output %X{traceId} and %X{spanId} populated by Micrometer Tracing.",
                "%d{yyyy-MM-dd HH:mm:ss.SSS} [%thread] [%X{traceId},%X{spanId}] %-5level %logger{36} - %msg%n",
                "Update logging pattern in logback.xml or application.yml.",
                "io.elmos.recipes.cloud.SpringCloudDistributedTracingRecipe",
                "Add traceId and spanId placeholders to logging pattern.",
                "Remove trace correlation from log pattern.",
                "https://micrometer.io/docs/tracing#_logging_pattern"
        ));
        register(new ModernizationRule(
                "CLD-030",
                RuleCategory.SPRING_CLOUD,
                "Microservice Graceful Teardown and Service Deregistration",
                RuleSeverity.MAJOR,
                2,
                "Ensure DiscoveryClient deregistration hook completes before server port shutdown occurs.",
                "server.shutdown=graceful\nspring.lifecycle.timeout-per-shutdown-phase=20s",
                "Configure graceful shutdown and phase timeout.",
                "io.elmos.worker.cloud.SpringCloudMicroservicesModernizer",
                "Add server.shutdown=graceful to application properties.",
                "Allow abrupt process termination.",
                "https://docs.spring.io/spring-boot/docs/current/reference/html/web.html#web.graceful-shutdown"
        ));
    }

    private static void initXmlRules() {
        register(new ModernizationRule(
                "XML-001",
                RuleCategory.XML_JAVACONFIG,
                "Legacy <beans> Root to @Configuration Class Migration",
                RuleSeverity.BLOCKER,
                4,
                "Convert legacy Spring XML beans configuration files to modern JavaConfig @Configuration classes.",
                "<beans xmlns=\"http://www.springframework.org/schema/beans\"> ... </beans>",
                "@Configuration\npublic class AppConfig { ... }",
                "io.elmos.worker.xml.SpringXmlToJavaConfigConverter",
                "Generate @Configuration Java class from root XML document.",
                "Retain legacy XML and import via @ImportResource.",
                "https://docs.spring.io/spring-framework/reference/core/beans/java/configuration-annotation.html"
        ));
        register(new ModernizationRule(
                "XML-002",
                RuleCategory.XML_JAVACONFIG,
                "Spring <bean> Declaration to @Bean Factory Method Migration",
                RuleSeverity.BLOCKER,
                3,
                "Convert <bean id=\"...\" class=\"...\"> elements to corresponding @Bean methods in @Configuration classes.",
                "<bean id=\"orderService\" class=\"com.example.OrderServiceImpl\"/>",
                "@Bean\npublic OrderService orderService() { return new OrderServiceImpl(); }",
                "io.elmos.worker.xml.SpringXmlToJavaConfigConverter",
                "Extract bean id and class, emitting @Bean method definition.",
                "Restore XML bean declaration.",
                "https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html"
        ));
        register(new ModernizationRule(
                "XML-003",
                RuleCategory.XML_JAVACONFIG,
                "<context:component-scan> to @ComponentScan Modernization",
                RuleSeverity.BLOCKER,
                2,
                "Convert <context:component-scan base-package=\"...\"/> to @ComponentScan(\"...\") annotation on configuration class.",
                "<context:component-scan base-package=\"com.example.app\"/>",
                "@ComponentScan(basePackages = \"com.example.app\")",
                "io.elmos.worker.xml.SpringXmlToJavaConfigConverter",
                "Emit @ComponentScan annotation on generated Java configuration.",
                "Restore XML component scan.",
                "https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html"
        ));
        register(new ModernizationRule(
                "XML-004",
                RuleCategory.XML_JAVACONFIG,
                "<tx:annotation-driven> to @EnableTransactionManagement",
                RuleSeverity.BLOCKER,
                2,
                "Convert <tx:annotation-driven transaction-manager=\"...\"/> to @EnableTransactionManagement annotation.",
                "<tx:annotation-driven transaction-manager=\"transactionManager\"/>",
                "@EnableTransactionManagement",
                "io.elmos.worker.xml.SpringXmlToJavaConfigConverter",
                "Add @EnableTransactionManagement to configuration class.",
                "Restore tx:annotation-driven in XML.",
                "https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html#transaction-declarative-annotations"
        ));
        register(new ModernizationRule(
                "XML-005",
                RuleCategory.XML_JAVACONFIG,
                "<mvc:annotation-driven> to @EnableWebMvc and WebMvcConfigurer",
                RuleSeverity.CRITICAL,
                3,
                "Convert <mvc:annotation-driven/> to @EnableWebMvc and WebMvcConfigurer bean implementation.",
                "<mvc:annotation-driven/>",
                "@EnableWebMvc\npublic class WebConfig implements WebMvcConfigurer { ... }",
                "io.elmos.worker.xml.SpringXmlToJavaConfigConverter",
                "Annotate configuration with @EnableWebMvc and implement WebMvcConfigurer.",
                "Restore mvc:annotation-driven in XML.",
                "https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config.html"
        ));
        register(new ModernizationRule(
                "XML-006",
                RuleCategory.XML_JAVACONFIG,
                "<context:property-placeholder> to @PropertySource",
                RuleSeverity.MAJOR,
                2,
                "Convert <context:property-placeholder location=\"...\"/> to @PropertySource(\"...\") or Spring Boot application.yml properties.",
                "<context:property-placeholder location=\"classpath:app.properties\"/>",
                "@PropertySource(\"classpath:app.properties\")",
                "io.elmos.worker.xml.SpringXmlToJavaConfigConverter",
                "Add @PropertySource annotation or migrate properties directly into application.properties.",
                "Restore XML property placeholder.",
                "https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html"
        ));
        register(new ModernizationRule(
                "XML-007",
                RuleCategory.XML_JAVACONFIG,
                "<aop:aspectj-autoproxy> to @EnableAspectJAutoProxy",
                RuleSeverity.MAJOR,
                2,
                "Convert <aop:aspectj-autoproxy proxy-target-class=\"true\"/> to @EnableAspectJAutoProxy(proxyTargetClass = true).",
                "<aop:aspectj-autoproxy proxy-target-class=\"true\"/>",
                "@EnableAspectJAutoProxy(proxyTargetClass = true)",
                "io.elmos.worker.xml.SpringXmlToJavaConfigConverter",
                "Add @EnableAspectJAutoProxy annotation.",
                "Restore aop:aspectj-autoproxy.",
                "https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html#aop-ataspectj-enabling"
        ));
        register(new ModernizationRule(
                "XML-008",
                RuleCategory.XML_JAVACONFIG,
                "<task:scheduler> and <task:executor> to @EnableScheduling / ThreadPoolTaskExecutor",
                RuleSeverity.MAJOR,
                3,
                "Convert <task:scheduler> and <task:executor> XML elements to @EnableScheduling, @EnableAsync and ThreadPoolTaskExecutor beans.",
                "<task:executor id=\"executor\" pool-size=\"5-25\" queue-capacity=\"100\"/>",
                "@Bean public Executor taskExecutor() { ThreadPoolTaskExecutor e = new ThreadPoolTaskExecutor(); e.setCorePoolSize(5); e.setMaxPoolSize(25); e.setQueueCapacity(100); return e; }",
                "io.elmos.worker.xml.SpringXmlToJavaConfigConverter",
                "Generate ThreadPoolTaskExecutor bean methods with configured pool bounds.",
                "Restore task executor XML.",
                "https://docs.spring.io/spring-framework/reference/integration/scheduling.html"
        ));
        register(new ModernizationRule(
                "XML-009",
                RuleCategory.XML_JAVACONFIG,
                "<bean class=\"...CommonsMultipartResolver\"> to StandardServletMultipartResolver",
                RuleSeverity.CRITICAL,
                2,
                "CommonsMultipartResolver was removed in Spring 6. Replace with StandardServletMultipartResolver @Bean.",
                "<bean id=\"multipartResolver\" class=\"org.springframework.web.multipart.commons.CommonsMultipartResolver\"/>",
                "@Bean public MultipartResolver multipartResolver() { return new StandardServletMultipartResolver(); }",
                "io.elmos.worker.xml.SpringXmlToJavaConfigConverter",
                "Replace CommonsMultipartResolver with StandardServletMultipartResolver.",
                "Restore commons file upload.",
                "https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html"
        ));
        register(new ModernizationRule(
                "XML-010",
                RuleCategory.XML_JAVACONFIG,
                "<bean class=\"...InternalResourceViewResolver\"> to ViewResolver Registry",
                RuleSeverity.MAJOR,
                2,
                "Convert InternalResourceViewResolver bean declaration into configureViewResolvers(ViewResolverRegistry registry) method.",
                "<bean class=\"org.springframework.web.servlet.view.InternalResourceViewResolver\"><property name=\"prefix\" value=\"/WEB-INF/jsp/\"/><property name=\"suffix\" value=\".jsp\"/></bean>",
                "public void configureViewResolvers(ViewResolverRegistry registry) { registry.jsp(\"/WEB-INF/jsp/\", \".jsp\"); }",
                "io.elmos.worker.xml.SpringXmlToJavaConfigConverter",
                "Implement configureViewResolvers on WebMvcConfigurer.",
                "Restore XML view resolver bean.",
                "https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/view-resolvers.html"
        ));
        register(new ModernizationRule(
                "XML-011",
                RuleCategory.XML_JAVACONFIG,
                "Bean Property Setter Injection to Constructor Injection",
                RuleSeverity.MAJOR,
                3,
                "Modernize <property name=\"...\" ref=\"...\"/> setter injection into idiomatic Java constructor parameter injection.",
                "<bean id=\"orderService\" class=\"OrderServiceImpl\"><property name=\"repo\" ref=\"orderRepo\"/></bean>",
                "public OrderServiceImpl(OrderRepository orderRepo) { this.orderRepo = orderRepo; }",
                "io.elmos.worker.xml.SpringXmlToJavaConfigConverter",
                "Generate constructors with required dependencies and make fields final.",
                "Restore setter injection methods.",
                "https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html#beans-constructor-injection"
        ));
        register(new ModernizationRule(
                "XML-012",
                RuleCategory.XML_JAVACONFIG,
                "Bean Constructor Arguments to Parameterized Constructor Injection",
                RuleSeverity.MAJOR,
                2,
                "Convert <constructor-arg ref=\"...\"/> and <constructor-arg value=\"...\"/> to JavaConfig method parameters.",
                "<bean id=\"service\" class=\"Service\"><constructor-arg ref=\"dao\"/></bean>",
                "@Bean public Service service(Dao dao) { return new Service(dao); }",
                "io.elmos.worker.xml.SpringXmlToJavaConfigConverter",
                "Map constructor-arg elements to parameters of the @Bean method.",
                "Restore XML constructor-arg tags.",
                "https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html"
        ));
        register(new ModernizationRule(
                "XML-013",
                RuleCategory.XML_JAVACONFIG,
                "Bean Init-Method / Destroy-Method to @PostConstruct / @PreDestroy",
                RuleSeverity.MAJOR,
                2,
                "Convert init-method=\"init\" and destroy-method=\"cleanup\" to @PostConstruct and @PreDestroy or @Bean(initMethod, destroyMethod).",
                "<bean id=\"client\" class=\"Client\" init-method=\"start\" destroy-method=\"stop\"/>",
                "@Bean(initMethod = \"start\", destroyMethod = \"stop\") public Client client() { return new Client(); }",
                "io.elmos.worker.xml.SpringXmlToJavaConfigConverter",
                "Add initMethod and destroyMethod attributes to @Bean annotation.",
                "Restore XML init/destroy method attributes.",
                "https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html#beans-factory-lifecycle"
        ));
        register(new ModernizationRule(
                "XML-014",
                RuleCategory.XML_JAVACONFIG,
                "Bean Autowire byName / byType to Explicit Bean Wiring",
                RuleSeverity.CRITICAL,
                2,
                "Eliminate obsolete autowire=\"byName\" / autowire=\"byType\" XML attributes in favor of explicit constructor injection.",
                "<bean id=\"service\" class=\"Service\" autowire=\"byType\"/>",
                "@Bean public Service service(Repository repo) { return new Service(repo); }",
                "io.elmos.worker.xml.SpringXmlToJavaConfigConverter",
                "Explicitly wire dependencies in @Bean factory method signature.",
                "Restore autowire byType in XML.",
                "https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-autowire.html"
        ));
        register(new ModernizationRule(
                "XML-015",
                RuleCategory.XML_JAVACONFIG,
                "Bean Scope Prototype / Singleton to @Scope Annotation",
                RuleSeverity.MINOR,
                1,
                "Convert scope=\"prototype\" XML attribute to @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE).",
                "<bean id=\"task\" class=\"Task\" scope=\"prototype\"/>",
                "@Bean @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE) public Task task() { return new Task(); }",
                "io.elmos.worker.xml.SpringXmlToJavaConfigConverter",
                "Add @Scope annotation to @Bean method.",
                "Restore XML scope attribute.",
                "https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html"
        ));
        register(new ModernizationRule(
                "XML-016",
                RuleCategory.XML_JAVACONFIG,
                "<import resource=\"...\"> to @Import Annotation",
                RuleSeverity.MAJOR,
                2,
                "Convert <import resource=\"services.xml\"/> to @Import(ServicesConfig.class) on Java configuration.",
                "<import resource=\"classpath:services.xml\"/>",
                "@Import(ServicesConfig.class)",
                "io.elmos.worker.xml.SpringXmlToJavaConfigConverter",
                "Translate XML import elements to @Import annotations on configuration classes.",
                "Restore XML import tags.",
                "https://docs.spring.io/spring-framework/reference/core/beans/java/composing-configuration-classes.html"
        ));
        register(new ModernizationRule(
                "XML-017",
                RuleCategory.XML_JAVACONFIG,
                "<mvc:interceptors> to WebMvcConfigurer.addInterceptors",
                RuleSeverity.MAJOR,
                2,
                "Convert <mvc:interceptors> XML definitions into addInterceptors(InterceptorRegistry registry) method.",
                "<mvc:interceptors><bean class=\"com.example.AuditInterceptor\"/></mvc:interceptors>",
                "public void addInterceptors(InterceptorRegistry registry) { registry.addInterceptor(new AuditInterceptor()); }",
                "io.elmos.worker.xml.SpringXmlToJavaConfigConverter",
                "Implement addInterceptors on WebMvcConfigurer.",
                "Restore mvc:interceptors in XML.",
                "https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/interceptors.html"
        ));
        register(new ModernizationRule(
                "XML-018",
                RuleCategory.XML_JAVACONFIG,
                "<mvc:resources> to WebMvcConfigurer.addResourceHandlers",
                RuleSeverity.MAJOR,
                2,
                "Convert <mvc:resources mapping=\"/static/**\" location=\"/static/\"/> to addResourceHandlers method.",
                "<mvc:resources mapping=\"/resources/**\" location=\"/resources/\"/>",
                "public void addResourceHandlers(ResourceHandlerRegistry registry) { registry.addResourceHandler(\"/resources/**\").addResourceLocations(\"/resources/\"); }",
                "io.elmos.worker.xml.SpringXmlToJavaConfigConverter",
                "Implement addResourceHandlers on WebMvcConfigurer.",
                "Restore mvc:resources in XML.",
                "https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html"
        ));
        register(new ModernizationRule(
                "XML-019",
                RuleCategory.XML_JAVACONFIG,
                "<mvc:cors> to WebMvcConfigurer.addCorsMappings",
                RuleSeverity.MAJOR,
                2,
                "Convert <mvc:cors> XML configuration into addCorsMappings(CorsRegistry registry) method.",
                "<mvc:cors><mvc:mapping path=\"/api/**\" allowed-origins=\"*\"/></mvc:cors>",
                "public void addCorsMappings(CorsRegistry registry) { registry.addMapping(\"/api/**\").allowedOrigins(\"*\"); }",
                "io.elmos.worker.xml.SpringXmlToJavaConfigConverter",
                "Implement addCorsMappings on WebMvcConfigurer.",
                "Restore mvc:cors in XML.",
                "https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/cors.html"
        ));
        register(new ModernizationRule(
                "XML-020",
                RuleCategory.XML_JAVACONFIG,
                "<mvc:message-converters> to WebMvcConfigurer.configureMessageConverters",
                RuleSeverity.MAJOR,
                2,
                "Convert <mvc:message-converters> into configureMessageConverters or extendMessageConverters method.",
                "<mvc:message-converters><bean class=\"org.springframework.http.converter.json.MappingJackson2HttpMessageConverter\"/></mvc:message-converters>",
                "public void extendMessageConverters(List<HttpMessageConverter<?>> converters) { converters.add(new MappingJackson2HttpMessageConverter()); }",
                "io.elmos.worker.xml.SpringXmlToJavaConfigConverter",
                "Implement extendMessageConverters on WebMvcConfigurer.",
                "Restore message converters in XML.",
                "https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/message-converters.html"
        ));
        register(new ModernizationRule(
                "XML-021",
                RuleCategory.XML_JAVACONFIG,
                "<util:list>, <util:map>, <util:set> to Java Collections Bean Definitions",
                RuleSeverity.MINOR,
                2,
                "Convert Spring util namespace collection beans to java.util.List, Map, Set @Bean methods using List.of(), Map.of().",
                "<util:list id=\"allowedRoles\"><value>ROLE_USER</value><value>ROLE_ADMIN</value></util:list>",
                "@Bean public List<String> allowedRoles() { return List.of(\"ROLE_USER\", \"ROLE_ADMIN\"); }",
                "io.elmos.worker.xml.SpringXmlToJavaConfigConverter",
                "Generate immutable List.of / Map.of collection @Bean definitions.",
                "Restore util:list XML tags.",
                "https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html#beans-collection-elements"
        ));
        register(new ModernizationRule(
                "XML-022",
                RuleCategory.XML_JAVACONFIG,
                "<util:properties> to @ConfigurationProperties / PropertiesFactoryBean",
                RuleSeverity.MINOR,
                2,
                "Convert <util:properties id=\"appProps\" location=\"...\"/> to typed @ConfigurationProperties or Properties bean.",
                "<util:properties id=\"appProps\" location=\"classpath:app.properties\"/>",
                "@Bean public PropertiesFactoryBean appProps() { PropertiesFactoryBean b = new PropertiesFactoryBean(); b.setLocation(new ClassPathResource(\"app.properties\")); return b; }",
                "io.elmos.worker.xml.SpringXmlToJavaConfigConverter",
                "Declare PropertiesFactoryBean or typed @ConfigurationProperties.",
                "Restore util:properties XML tags.",
                "https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html"
        ));
        register(new ModernizationRule(
                "XML-023",
                RuleCategory.XML_JAVACONFIG,
                "Legacy JDBC DriverManagerDataSource to HikariDataSource Pool",
                RuleSeverity.CRITICAL,
                3,
                "Replace unpooled org.springframework.jdbc.datasource.DriverManagerDataSource with com.zaxxer.hikari.HikariDataSource.",
                "<bean id=\"dataSource\" class=\"org.springframework.jdbc.datasource.DriverManagerDataSource\"> ... </bean>",
                "@Bean public DataSource dataSource() { HikariDataSource ds = new HikariDataSource(); ds.setJdbcUrl(url); ds.setUsername(user); ds.setPassword(pass); return ds; }",
                "io.elmos.worker.xml.SpringXmlToJavaConfigConverter",
                "Replace unpooled dataSource bean with HikariDataSource production pool.",
                "Restore unpooled DriverManagerDataSource.",
                "https://github.com/brettwooldridge/HikariCP"
        ));
        register(new ModernizationRule(
                "XML-024",
                RuleCategory.XML_JAVACONFIG,
                "LocalSessionFactoryBean to LocalContainerEntityManagerFactoryBean",
                RuleSeverity.CRITICAL,
                3,
                "Migrate legacy Hibernate LocalSessionFactoryBean XML declarations to modern JPA LocalContainerEntityManagerFactoryBean.",
                "<bean id=\"sessionFactory\" class=\"org.springframework.orm.hibernate5.LocalSessionFactoryBean\"> ... </bean>",
                "@Bean public LocalContainerEntityManagerFactoryBean entityManagerFactory(DataSource dataSource) { ... }",
                "io.elmos.worker.xml.SpringXmlToJavaConfigConverter",
                "Migrate SessionFactory to JPA EntityManagerFactory.",
                "Restore LocalSessionFactoryBean.",
                "https://docs.spring.io/spring-framework/reference/data-access/orm/jpa.html#orm-jpa-setup-lcemfb"
        ));
        register(new ModernizationRule(
                "XML-025",
                RuleCategory.XML_JAVACONFIG,
                "Elimination of web.xml ContextLoaderListener via SpringBootServletInitializer",
                RuleSeverity.CRITICAL,
                3,
                "Remove legacy web.xml ContextLoaderListener and DispatcherServlet mappings by extending SpringBootServletInitializer.",
                "<listener><listener-class>org.springframework.web.context.ContextLoaderListener</listener-class></listener>",
                "public class ServletInitializer extends SpringBootServletInitializer { @Override protected SpringApplicationBuilder configure(SpringApplicationBuilder application) { return application.sources(Application.class); } }",
                "io.elmos.worker.xml.SpringXmlToJavaConfigConverter",
                "Delete web.xml and provide SpringBootServletInitializer class for embedded / WAR execution.",
                "Restore web.xml deployment descriptor.",
                "https://docs.spring.io/spring-boot/docs/current/reference/html/howto.html#howto.traditional-deployment"
        ));
    }

    private static void initCoreRules() {
        register(new ModernizationRule(
                "COR-001",
                RuleCategory.CORE_FRAMEWORK,
                "JSR-305 Nullability Annotations to JSpecify @NonNull / @Nullable",
                RuleSeverity.MAJOR,
                2,
                "Spring Framework 6 deprecates JSR-305 javax.annotation.Nullable in favor of standard JSpecify org.jspecify.annotations.Nullable.",
                "import javax.annotation.Nullable;",
                "import org.jspecify.annotations.Nullable;",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Replace javax.annotation.Nullable with org.jspecify.annotations.Nullable.",
                "Restore javax.annotation imports.",
                "https://jspecify.dev/"
        ));
        register(new ModernizationRule(
                "COR-002",
                RuleCategory.CORE_FRAMEWORK,
                "PathPatternParser Default Route Matching Alignment",
                RuleSeverity.CRITICAL,
                3,
                "Spring MVC 6 uses PathPatternParser by default instead of AntPathMatcher. Disallows certain wildcard combinations like /**/foo.",
                "spring.mvc.pathmatch.matching-strategy=ant-path-matcher",
                "Align URL route patterns with PathPatternParser syntax.",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Normalize URL patterns or set matching-strategy=path-pattern-parser.",
                "Revert matching-strategy to ant-path-matcher.",
                "https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html#mvc-ann-requestmapping-patterns"
        ));
        register(new ModernizationRule(
                "COR-003",
                RuleCategory.CORE_FRAMEWORK,
                "Trailing Slash URL Matching Deprecation Elimination",
                RuleSeverity.MAJOR,
                2,
                "Trailing slash matching (/api/users/ matching /api/users) is disabled by default in Spring 6. Explicitly configure route mappings.",
                "@GetMapping(\"/users\")",
                "@GetMapping({\"/users\", \"/users/\"}) or configure strict routing",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Explicitly match required URL paths without relying on automatic trailing slash redirection.",
                "Re-enable trailing slash match via configurePathMatch.",
                "https://github.com/spring-projects/spring-framework/issues/28552"
        ));
        register(new ModernizationRule(
                "COR-004",
                RuleCategory.CORE_FRAMEWORK,
                "RestTemplate Modernization to RestClient",
                RuleSeverity.CRITICAL,
                3,
                "Spring Framework 6.1 introduces RestClient, offering a modern fluent synchronous HTTP client API over RestTemplate.",
                "RestTemplate restTemplate = new RestTemplate(); Product p = restTemplate.getForObject(url, Product.class);",
                "RestClient restClient = RestClient.create(); Product p = restClient.get().uri(url).retrieve().body(Product.class);",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Migrate RestTemplate calls to fluent RestClient.",
                "Keep legacy RestTemplate.",
                "https://docs.spring.io/spring-framework/reference/integration/rest-clients.html#rest-restclient"
        ));
        register(new ModernizationRule(
                "COR-005",
                RuleCategory.CORE_FRAMEWORK,
                "Apache HttpComponents HttpClient 4.x to HttpClient 5.x",
                RuleSeverity.CRITICAL,
                3,
                "Update Apache HttpClient from org.apache.http (4.x) to org.apache.hc.client5 (5.x) required by Spring 6.",
                "import org.apache.http.impl.client.CloseableHttpClient;",
                "import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Update HttpClient imports and configuration to HC5.",
                "Restore HttpClient 4.x.",
                "https://hc.apache.org/httpcomponents-client-5.2.x/migration-to-5.x.html"
        ));
        register(new ModernizationRule(
                "COR-006",
                RuleCategory.CORE_FRAMEWORK,
                "Jackson 2.15+ StreamReadConstraints and Datatype Modules",
                RuleSeverity.MAJOR,
                2,
                "Jackson 2.15+ introduces max string length and number length constraints (StreamReadConstraints). Configure ObjectMapper accordingly.",
                "ObjectMapper mapper = new ObjectMapper();",
                "ObjectMapper mapper = JsonMapper.builder().streamReadConstraints(StreamReadConstraints.builder().maxStringLength(20_000_000).build()).build();",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Calibrate Jackson StreamReadConstraints on ObjectMapper builder.",
                "Restore default ObjectMapper constraints.",
                "https://github.com/FasterXML/jackson-core/issues/827"
        ));
        register(new ModernizationRule(
                "COR-007",
                RuleCategory.CORE_FRAMEWORK,
                "Strict RFC URL Parsing and Matrix Variable Normalization",
                RuleSeverity.MAJOR,
                2,
                "Spring 6 strictly adheres to RFC 3986 URL parsing rules. Reject unencoded characters in path or query strings.",
                "Enable URI encoding on client requests: URLEncoder.encode(param, StandardCharsets.UTF_8)",
                "Ensure client requests encode all query parameters according to RFC 3986.",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Add client URI encoding filter or parameter sanitization.",
                "Allow relaxed URI characters in embedded Tomcat.",
                "https://tomcat.apache.org/tomcat-10.1-doc/config/http.html#Standard_Implementation"
        ));
        register(new ModernizationRule(
                "COR-008",
                RuleCategory.CORE_FRAMEWORK,
                "Reactive Netty 4.1.x / Reactor 3.6 Event Loop Upgrades",
                RuleSeverity.MAJOR,
                3,
                "Update Netty and Project Reactor dependencies to support Java 21 Epoll and modern backpressure signals.",
                "reactor.core.publisher.Flux / Mono",
                "Ensure non-blocking operations do not execute blocking database calls without Schedulers.boundedElastic().",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Offload blocking calls in reactive pipelines to Schedulers.boundedElastic().",
                "Run blocking calls on event loop (causes starvation).",
                "https://projectreactor.io/docs/core/release/reference/#schedulers"
        ));
        register(new ModernizationRule(
                "COR-009",
                RuleCategory.CORE_FRAMEWORK,
                "Virtual Thread Executor Support with Java 21 TaskExecutors",
                RuleSeverity.MAJOR,
                2,
                "Enable virtual threads in Spring Boot 3.2+ / 4.x using spring.threads.virtual.enabled=true for high concurrency.",
                "spring.threads.virtual.enabled=true",
                "Add spring.threads.virtual.enabled=true in application.properties.",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Enable virtual threads property to use Java 21 lightweight virtual thread pool.",
                "Disable virtual threads and use platform thread pool.",
                "https://docs.spring.io/spring-boot/docs/current/reference/html/features.html#features.spring-application.virtual-threads"
        ));
        register(new ModernizationRule(
                "COR-010",
                RuleCategory.CORE_FRAMEWORK,
                "javax.validation to jakarta.validation Validation API Migration",
                RuleSeverity.BLOCKER,
                3,
                "Migrate Hibernate Validator and Bean Validation annotations from javax.validation.* to jakarta.validation.*.",
                "import javax.validation.constraints.*;",
                "import jakarta.validation.constraints.*;",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Replace javax.validation imports with jakarta.validation.",
                "Restore javax.validation imports.",
                "https://jakarta.ee/specifications/bean-validation/3.0/"
        ));
        register(new ModernizationRule(
                "COR-011",
                RuleCategory.CORE_FRAMEWORK,
                "Spring Expression Language (SpEL) Compilation CompilerMode",
                RuleSeverity.MAJOR,
                2,
                "Configure SpEL CompilerMode.IMMEDIATE for performance-critical expression evaluations.",
                "SpelParserConfiguration config = new SpelParserConfiguration(SpelCompilerMode.IMMEDIATE, this.getClass().getClassLoader());",
                "Set SpelCompilerMode.IMMEDIATE in SpelParserConfiguration.",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Enable compiled SpEL mode for high-frequency expressions.",
                "Use interpreted SpEL mode.",
                "https://docs.spring.io/spring-framework/reference/core/expressions/language-ref.html#expressions-spel-compilation"
        ));
        register(new ModernizationRule(
                "COR-012",
                RuleCategory.CORE_FRAMEWORK,
                "Spring CacheManager RedisCacheConfiguration Serialization",
                RuleSeverity.MAJOR,
                2,
                "Configure GenericJackson2JsonRedisSerializer with JavaTimeModule on RedisCacheConfiguration.",
                "RedisCacheConfiguration.defaultCacheConfig().serializeValuesWith(RedisSerializationContext.SerializationPair.fromSerializer(new GenericJackson2JsonRedisSerializer()));",
                "Apply JSON serializer with Java 8 time support to RedisCacheManager.",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Configure RedisCacheConfiguration with JSON value serializer.",
                "Use default Java binary serialization.",
                "https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html"
        ));
        register(new ModernizationRule(
                "COR-013",
                RuleCategory.CORE_FRAMEWORK,
                "Spring Event Publisher Generic ApplicationEvent Listeners",
                RuleSeverity.MINOR,
                2,
                "Modernize @EventListener methods to consume domain POJOs directly without extending ApplicationEvent.",
                "public class OrderEvent extends ApplicationEvent",
                "public record OrderEvent(Long orderId, BigDecimal amount) {} // @EventListener void onOrder(OrderEvent e)",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Migrate event classes to plain records and consume via @EventListener.",
                "Restore ApplicationEvent class hierarchy.",
                "https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events-annotation"
        ));
        register(new ModernizationRule(
                "COR-014",
                RuleCategory.CORE_FRAMEWORK,
                "Environment Profiles and Custom ProfileExpression Evaluation",
                RuleSeverity.MINOR,
                1,
                "Use profile expressions (e.g. @Profile(\"prod & !cloud\")) with Spring 6 boolean operators.",
                "@Profile(\"prod\")",
                "@Profile(\"prod & !cloud\")",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Refactor complex profile checks to use boolean expressions.",
                "Restore single profile names.",
                "https://docs.spring.io/spring-framework/reference/core/beans/environment.html#beans-definition-profiles-java"
        ));
        register(new ModernizationRule(
                "COR-015",
                RuleCategory.CORE_FRAMEWORK,
                "ResourceLoader ClassPath / FileSystem Path Resolution",
                RuleSeverity.MINOR,
                1,
                "Modernize resource loading using Spring ResourceLoader with classpath: and file: prefixes safely.",
                "resourceLoader.getResource(\"classpath:config/schema.json\");",
                "Verify Resource.exists() and use try-with-resources on Resource.getInputStream().",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Add defensive resource stream closing.",
                "Leave resource streams unclosed.",
                "https://docs.spring.io/spring-framework/reference/core/resources.html"
        ));
        register(new ModernizationRule(
                "COR-016",
                RuleCategory.CORE_FRAMEWORK,
                "ConversionService Generic Converter / Formatter Registration",
                RuleSeverity.MAJOR,
                2,
                "Register custom GenericConverter beans into FormatterRegistry via WebMvcConfigurer.addFormatters.",
                "public void addFormatters(FormatterRegistry registry) { registry.addConverter(new StringToEnumConverter()); }",
                "Implement addFormatters on WebMvcConfigurer.",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Register custom type converters in WebMvcConfigurer.",
                "Restore XML ConversionService bean.",
                "https://docs.spring.io/spring-framework/reference/core/validation/convert.html"
        ));
        register(new ModernizationRule(
                "COR-017",
                RuleCategory.CORE_FRAMEWORK,
                "MethodParameter Named Parameter Extraction ASM Upgrades",
                RuleSeverity.CRITICAL,
                2,
                "Spring 6 no longer supports bytecode parameter name discovery without the -parameters javac compiler flag.",
                "<compilerArgs><arg>-parameters</arg></compilerArgs>",
                "Add -parameters compiler argument in maven-compiler-plugin configuration.",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Configure maven-compiler-plugin with <parameters>true</parameters>.",
                "Remove -parameters flag.",
                "https://github.com/spring-projects/spring-framework/wiki/Upgrading-to-Spring-Framework-6.x#parameter-name-retention"
        ));
        register(new ModernizationRule(
                "COR-018",
                RuleCategory.CORE_FRAMEWORK,
                "Default Parameter Resolution with -parameters Compiler Flag",
                RuleSeverity.CRITICAL,
                2,
                "Ensure all @RequestParam, @PathVariable, and @RequestHeader annotations explicitly specify parameter names if not using -parameters.",
                "@PathVariable String id",
                "@PathVariable(\"id\") String id",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Add explicit name attribute to web parameter annotations.",
                "Remove explicit name attributes.",
                "https://github.com/spring-projects/spring-framework/wiki/Upgrading-to-Spring-Framework-6.x#parameter-name-retention"
        ));
        register(new ModernizationRule(
                "COR-019",
                RuleCategory.CORE_FRAMEWORK,
                "Spring TypeSystem ResolvableType Deep Generic Inspection",
                RuleSeverity.MAJOR,
                2,
                "Replace custom reflection logic with Spring ResolvableType.forClass(clazz).getGeneric(...) for generic type resolution.",
                "ResolvableType t = ResolvableType.forField(field); Class<?> genericType = t.getGeneric(0).resolve();",
                "Use ResolvableType for type introspection.",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Replace java.lang.reflect.ParameterizedType inspection with ResolvableType.",
                "Restore manual reflection.",
                "https://docs.spring.io/spring-framework/reference/core/beans/resolvable-type.html"
        ));
        register(new ModernizationRule(
                "COR-020",
                RuleCategory.CORE_FRAMEWORK,
                "Asynchronous Task Execution Exception Handling Decorator",
                RuleSeverity.MAJOR,
                2,
                "Implement AsyncUncaughtExceptionHandler for @Async methods returning void.",
                "public class CustomAsyncExceptionHandler implements AsyncUncaughtExceptionHandler",
                "Override getAsyncUncaughtExceptionHandler() in AsyncConfigurer.",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Configure AsyncUncaughtExceptionHandler on AsyncConfigurer.",
                "Allow uncaught async exceptions to be silently dropped.",
                "https://docs.spring.io/spring-framework/reference/integration/scheduling.html#scheduling-annotation-support-async"
        ));
    }

    private static void initActuatorRules() {
        register(new ModernizationRule(
                "ACT-001",
                RuleCategory.ACTUATOR_OBSERVABILITY,
                "Management Server Base Path and Port Isolation Configuration",
                RuleSeverity.CRITICAL,
                2,
                "Isolate management endpoints on a distinct port (e.g. management.server.port=8081) and path (/actuator).",
                "management.server.port=8081\nmanagement.endpoints.web.base-path=/actuator",
                "Configure management port and base path in application.yml.",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Set management.server.port and base-path properties.",
                "Expose actuator on main application port without isolation.",
                "https://docs.spring.io/spring-boot/docs/current/reference/html/actuator.html#actuator.monitoring.customizing-management-server-port"
        ));
        register(new ModernizationRule(
                "ACT-002",
                RuleCategory.ACTUATOR_OBSERVABILITY,
                "Health Indicator Imperative and Reactive Modernization",
                RuleSeverity.MAJOR,
                2,
                "Implement modern HealthIndicator or ReactiveHealthIndicator with Health.up().withDetail(...) semantics.",
                "@Component public class DatabaseHealthIndicator implements HealthIndicator { public Health health() { return Health.up().build(); } }",
                "Return typed Health status with diagnostic details.",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Provide HealthIndicator component.",
                "Remove health indicator.",
                "https://docs.spring.io/spring-boot/docs/current/reference/html/actuator.html#actuator.endpoints.health.auto-configured-health-indicators"
        ));
        register(new ModernizationRule(
                "ACT-003",
                RuleCategory.ACTUATOR_OBSERVABILITY,
                "Micrometer Prometheus MeterRegistry Metric Formatting",
                RuleSeverity.MAJOR,
                2,
                "Configure PrometheusMeterRegistry with common tags (application, environment, region).",
                "management.prometheus.metrics.export.enabled=true\nmanagement.metrics.tags.application=${spring.application.name}",
                "Add Prometheus meter registry configuration and common tags.",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Enable Prometheus export and common metric tags.",
                "Disable Prometheus metrics.",
                "https://docs.spring.io/spring-boot/docs/current/reference/html/actuator.html#actuator.metrics.export.prometheus"
        ));
        register(new ModernizationRule(
                "ACT-004",
                RuleCategory.ACTUATOR_OBSERVABILITY,
                "OpenTelemetry OTLP Exporter Tracing & Metric Pipeline",
                RuleSeverity.CRITICAL,
                3,
                "Configure OTLP gRPC/HTTP exporter endpoint for OpenTelemetry traces and metrics.",
                "management.otlp.tracing.endpoint=http://otel-collector:4318/v1/traces",
                "Configure OTLP endpoint in application.yml.",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Set management.otlp.tracing.endpoint in properties.",
                "Remove OTLP exporter.",
                "https://docs.spring.io/spring-boot/docs/current/reference/html/actuator.html#actuator.micrometer-tracing.tracer-implementations.otlp"
        ));
        register(new ModernizationRule(
                "ACT-005",
                RuleCategory.ACTUATOR_OBSERVABILITY,
                "GraalVM Native Image RuntimeHintsRegistrar Configuration",
                RuleSeverity.MAJOR,
                3,
                "Register dynamic reflection and resource access hints via RuntimeHintsRegistrar for AOT compilation.",
                "public class CustomRuntimeHints implements RuntimeHintsRegistrar { public void registerHints(RuntimeHints hints, ClassLoader loader) { ... } }",
                "Implement RuntimeHintsRegistrar and register via @ImportRuntimeHints.",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Provide RuntimeHintsRegistrar implementation.",
                "Rely on automatic AOT inference (may fail at runtime).",
                "https://docs.spring.io/spring-framework/reference/core/aot.html#aot.hints"
        ));
        register(new ModernizationRule(
                "ACT-006",
                RuleCategory.ACTUATOR_OBSERVABILITY,
                "Spring Boot Docker Compose Development Integration",
                RuleSeverity.MINOR,
                2,
                "Use spring-boot-docker-compose for zero-config local dependency container initialization in development.",
                "<artifactId>spring-boot-docker-compose</artifactId>",
                "Add docker-compose dependency with spring.docker.compose.lifecycle-management=start-and-stop.",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Include spring-boot-docker-compose development dependency.",
                "Remove docker-compose integration.",
                "https://docs.spring.io/spring-boot/docs/current/reference/html/features.html#features.docker-compose"
        ));
        register(new ModernizationRule(
                "ACT-007",
                RuleCategory.ACTUATOR_OBSERVABILITY,
                "Container Lifecycle Graceful Shutdown server.shutdown=graceful",
                RuleSeverity.CRITICAL,
                2,
                "Enable graceful shutdown to allow active HTTP requests and background tasks to complete before container termination.",
                "server.shutdown=graceful\nspring.lifecycle.timeout-per-shutdown-phase=30s",
                "Configure graceful shutdown in application.properties.",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Add server.shutdown=graceful and phase timeout.",
                "Allow abrupt SIGKILL termination.",
                "https://docs.spring.io/spring-boot/docs/current/reference/html/web.html#web.graceful-shutdown"
        ));
        register(new ModernizationRule(
                "ACT-008",
                RuleCategory.ACTUATOR_OBSERVABILITY,
                "Liveness and Readiness Probe Actuator Endpoints",
                RuleSeverity.CRITICAL,
                2,
                "Enable Kubernetes liveness and readiness probe endpoints: /actuator/health/liveness, /actuator/health/readiness.",
                "management.endpoint.health.probes.enabled=true",
                "Set management.endpoint.health.probes.enabled=true in application properties.",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Enable health probes for container orchestrators.",
                "Disable health probes.",
                "https://docs.spring.io/spring-boot/docs/current/reference/html/actuator.html#actuator.endpoints.health.kubernetes-probes"
        ));
        register(new ModernizationRule(
                "ACT-009",
                RuleCategory.ACTUATOR_OBSERVABILITY,
                "Actuator AuditEventRepository Persistence Modernization",
                RuleSeverity.MAJOR,
                2,
                "Implement durable AuditEventRepository @Bean storing security and operational audit events.",
                "@Bean public AuditEventRepository auditEventRepository() { return new CustomDatabaseAuditEventRepository(jdbcTemplate); }",
                "Provide durable AuditEventRepository implementation.",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Declare persistent AuditEventRepository bean.",
                "Use default InMemoryAuditEventRepository.",
                "https://docs.spring.io/spring-boot/docs/current/reference/html/actuator.html#actuator.auditing"
        ));
        register(new ModernizationRule(
                "ACT-010",
                RuleCategory.ACTUATOR_OBSERVABILITY,
                "Heap Dump / Thread Dump Endpoint Security Restriction",
                RuleSeverity.CRITICAL,
                2,
                "Ensure heapdump and threaddump endpoints are restricted to administrative roles or disabled in production.",
                "management.endpoints.web.exposure.exclude=heapdump",
                "Exclude sensitive diagnostic endpoints or require ROLE_ADMIN.",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Configure endpoint exclusion in production profile.",
                "Expose heapdump publicly without authentication.",
                "https://docs.spring.io/spring-boot/docs/current/reference/html/actuator.html#actuator.endpoints.exposing"
        ));
        register(new ModernizationRule(
                "ACT-011",
                RuleCategory.ACTUATOR_OBSERVABILITY,
                "Logback / Log4j2 Color Output and Structured JSON Logging",
                RuleSeverity.MAJOR,
                2,
                "Configure structured JSON logging with ECS or Logstash layout for centralized log aggregation.",
                "logging.structured.format.console=ecs",
                "Enable Spring Boot 3.4+ structured logging in application.yml.",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Set logging.structured.format.console=ecs.",
                "Use standard plain text logging.",
                "https://docs.spring.io/spring-boot/docs/current/reference/html/features.html#features.logging.structured"
        ));
        register(new ModernizationRule(
                "ACT-012",
                RuleCategory.ACTUATOR_OBSERVABILITY,
                "Distributed Trace Baggage Field Propagation Configuration",
                RuleSeverity.MAJOR,
                2,
                "Configure Micrometer Tracing baggage fields (e.g. tenant-id, request-id) for remote network propagation.",
                "management.tracing.baggage.remote-fields=tenant-id,user-id\nmanagement.tracing.baggage.correlation.fields=tenant-id,user-id",
                "Declare remote baggage fields in application properties.",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Set management.tracing.baggage properties.",
                "Disable baggage propagation.",
                "https://micrometer.io/docs/tracing#_baggage"
        ));
        register(new ModernizationRule(
                "ACT-013",
                RuleCategory.ACTUATOR_OBSERVABILITY,
                "JVM Memory and Garbage Collection Telemetry Metrics",
                RuleSeverity.MAJOR,
                2,
                "Configure JVM memory pool, GC pause, and thread count telemetry metrics for Grafana dashboards.",
                "management.metrics.enable.jvm=true",
                "Enable JVM metric binders in application properties.",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Ensure JVM metrics are enabled in actuator configuration.",
                "Disable JVM metrics.",
                "https://docs.spring.io/spring-boot/docs/current/reference/html/actuator.html#actuator.metrics.supported.jvm"
        ));
        register(new ModernizationRule(
                "ACT-014",
                RuleCategory.ACTUATOR_OBSERVABILITY,
                "SSL / TLS 1.3 KeyStore and TrustStore Modernization",
                RuleSeverity.CRITICAL,
                3,
                "Configure server.ssl with PKCS12 keystore and strict TLS 1.3 protocol suite for zero-trust microservice networks.",
                "server.ssl.enabled-protocols=TLSv1.3\nserver.ssl.key-store-type=PKCS12",
                "Set TLSv1.3 and PKCS12 keystore type in application properties.",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Enforce TLSv1.3 on embedded web server.",
                "Allow legacy TLSv1.0/1.1 protocols.",
                "https://docs.spring.io/spring-boot/docs/current/reference/html/web.html#web.server.ssl"
        ));
        register(new ModernizationRule(
                "ACT-015",
                RuleCategory.ACTUATOR_OBSERVABILITY,
                "Production Readiness Review Scorecard Automated Probe",
                RuleSeverity.MAJOR,
                2,
                "Automated composite check validating health indicators, metric exporters, and security postures before traffic routing.",
                "Perform composite preflight probe against /actuator/health, /actuator/prometheus, and /actuator/info.",
                "Execute preflight probe and verify HTTP 200 with status UP.",
                "io.elmos.worker.SpringDiagnosticAutoRepairer",
                "Include automated preflight verification probe in CI/CD deployment pipeline.",
                "Deploy without readiness probe.",
                "https://docs.spring.io/spring-boot/docs/current/reference/html/actuator.html#actuator.endpoints.health"
        ));
    }

    private SpringModernizationRulebookCatalog() {}

    private static void register(ModernizationRule rule) {
        RULES_BY_ID.put(rule.ruleId(), rule);
        RULES_BY_CATEGORY.computeIfAbsent(rule.category(), k -> new ArrayList<>()).add(rule);
    }

    public static List<ModernizationRule> getAllRules() {
        return List.copyOf(RULES_BY_ID.values());
    }

    public static Optional<ModernizationRule> getRule(String ruleId) {
        return Optional.ofNullable(RULES_BY_ID.get(ruleId));
    }

    public static List<ModernizationRule> findByCategory(RuleCategory category) {
        return List.copyOf(RULES_BY_CATEGORY.getOrDefault(category, List.of()));
    }

    public static List<ModernizationRule> findBySeverity(RuleSeverity severity) {
        return RULES_BY_ID.values().stream()
                .filter(r -> r.severity() == severity)
                .toList();
    }

    public static List<ModernizationRule> search(String keyword) {
        if (keyword == null || keyword.isBlank()) {
            return getAllRules();
        }
        String lower = keyword.toLowerCase();
        return RULES_BY_ID.values().stream()
                .filter(r -> r.ruleId().toLowerCase().contains(lower)
                        || r.name().toLowerCase().contains(lower)
                        || r.description().toLowerCase().contains(lower)
                        || r.sourcePattern().toLowerCase().contains(lower))
                .toList();
    }

    public static List<ModernizationRule> analyzeSourceCode(String sourceContent) {
        if (sourceContent == null || sourceContent.isBlank()) {
            return List.of();
        }
        return RULES_BY_ID.values().stream()
                .filter(r -> r.matches(sourceContent))
                .toList();
    }

    public static CatalogStatistics getSummaryStatistics() {
        int totalHours = RULES_BY_ID.values().stream().mapToInt(ModernizationRule::effortHours).sum();
        Map<RuleCategory, Integer> catCounts = new EnumMap<>(RuleCategory.class);
        for (RuleCategory cat : RuleCategory.values()) {
            catCounts.put(cat, findByCategory(cat).size());
        }
        Map<RuleSeverity, Integer> sevCounts = new EnumMap<>(RuleSeverity.class);
        for (RuleSeverity sev : RuleSeverity.values()) {
            sevCounts.put(sev, findBySeverity(sev).size());
        }
        return new CatalogStatistics(RULES_BY_ID.size(), totalHours, catCounts, sevCounts);
    }

    public static String generateMarkdownCatalog() {
        StringBuilder sb = new StringBuilder();
        sb.append("# Spring Modernization Rulebook Enterprise Catalog\n\n");
        CatalogStatistics stats = getSummaryStatistics();
        sb.append(String.format("Total Rules: **%d** | Total Estimated Effort: **%d hours**\n\n",
                stats.totalRules(), stats.totalEffortHours()));

        sb.append("## Category Breakdown\n\n");
        for (RuleCategory cat : RuleCategory.values()) {
            sb.append(String.format("- **%s**: %d rules\n", cat.getDisplayName(), stats.countByCategory().getOrDefault(cat, 0)));
        }
        sb.append("\n## Detailed Rulebook Registry\n\n");

        for (ModernizationRule rule : getAllRules()) {
            sb.append(String.format("### [%s] %s\n\n", rule.ruleId(), rule.name()));
            sb.append(String.format("- **Category**: %s\n", rule.category().getDisplayName()));
            sb.append(String.format("- **Severity**: `%s` (Effort: %d hours)\n", rule.severity(), rule.effortHours()));
            sb.append(String.format("- **Description**: %s\n", rule.description()));
            sb.append(String.format("- **Source Pattern**: `%s`\n", rule.sourcePattern()));
            sb.append(String.format("- **Recipe / Modernizer**: `%s`\n", rule.recipeOrModernizerClass()));
            sb.append(String.format("- **Remediation**: %s\n", rule.remediationGuidance()));
            sb.append(String.format("- **Rollback**: %s\n", rule.rollbackProcedure()));
            sb.append(String.format("- **Documentation**: [%s](%s)\n\n", rule.documentationUrl(), rule.documentationUrl()));
        }

        return sb.toString();
    }
}
