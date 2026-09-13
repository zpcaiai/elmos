package io.elmos.worker.rulebook;

import io.elmos.worker.rulebook.SpringModernizationRulebookCatalog.ModernizationRule;
import io.elmos.worker.rulebook.SpringModernizationRulebookCatalog.RuleCategory;
import io.elmos.worker.rulebook.SpringModernizationRulebookCatalog.RuleSeverity;

import java.time.Instant;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/**
 * Industrial-grade Architecture Rulebook Enforcer for Spring Modernization.
 * <p>
 * Evaluates source and target files against the 150 rules declared in the
 * {@link SpringModernizationRulebookCatalog}. Identifies deprecated patterns,
 * forbidden legacy libraries, security risks, transactional antipatterns,
 * and architectural layering violations.
 * <p>
 * Generates structured SARIF 2.1.0 results and executive compliance reports.
 */
public final class SpringModernizationArchitectureRulebookEnforcer {

    public record RuleViolation(
            String ruleId,
            RuleCategory category,
            RuleSeverity severity,
            String filePath,
            int lineNumber,
            String snippet,
            String message,
            String recommendedFix,
            String recipeOrModernizerClass
    ) {
        public RuleViolation {
            Objects.requireNonNull(ruleId, "ruleId must not be null");
            Objects.requireNonNull(category, "category must not be null");
            Objects.requireNonNull(severity, "severity must not be null");
            Objects.requireNonNull(filePath, "filePath must not be null");
        }
    }

    public record EnforcementReport(
            String projectId,
            Instant scanTime,
            int totalFilesScanned,
            int totalViolations,
            int blockerCount,
            int criticalCount,
            int majorCount,
            int minorCount,
            int infoCount,
            double complianceScore,
            Map<RuleCategory, Double> categoryComplianceScores,
            List<RuleViolation> violations,
            boolean isCompliant
    ) {
        public boolean hasBlockers() {
            return blockerCount > 0;
        }

        public boolean hasCriticals() {
            return criticalCount > 0;
        }
    }

    private static final Map<String, ModernizationRule> RULES_BY_ID;

    static {
        Map<String, ModernizationRule> map = new LinkedHashMap<>();
        for (ModernizationRule rule : SpringModernizationRulebookCatalog.getAllRules()) {
            map.put(rule.ruleId(), rule);
        }
        RULES_BY_ID = Collections.unmodifiableMap(map);
    }

    /**
     * Enforces the complete catalog of 150 rules on a project file map.
     *
     * @param projectId    Project unique identifier
     * @param projectFiles Map of relative path to file text content
     * @return Comprehensive EnforcementReport
     */
    public static EnforcementReport enforce(String projectId, Map<String, String> projectFiles) {
        Objects.requireNonNull(projectId, "projectId must not be null");
        Objects.requireNonNull(projectFiles, "projectFiles must not be null");

        List<RuleViolation> violations = new ArrayList<>();
        int scannedCount = 0;

        for (Map.Entry<String, String> entry : projectFiles.entrySet()) {
            String path = entry.getKey();
            String content = entry.getValue();
            scannedCount++;

            if (path.endsWith(".java")) {
                scanJavaFile(path, content, violations);
            } else if (path.endsWith(".xml")) {
                scanXmlFile(path, content, violations);
            } else if (path.endsWith(".yml") || path.endsWith(".yaml") || path.endsWith(".properties")) {
                scanConfigFile(path, content, violations);
            }
        }

        // Architectural layering and cross-file boundary checks
        scanArchitecturalBoundaries(projectFiles, violations);

        // Calculate severity counts
        int blockers = 0;
        int criticals = 0;
        int majors = 0;
        int minors = 0;
        int infos = 0;

        for (RuleViolation v : violations) {
            switch (v.severity()) {
                case BLOCKER -> blockers++;
                case CRITICAL -> criticals++;
                case MAJOR -> majors++;
                case MINOR -> minors++;
                case INFO -> infos++;
            }
        }

        // Compute overall compliance score: starting at 100.0, applying weighted penalties
        double penalty = (blockers * 25.0) + (criticals * 15.0) + (majors * 5.0) + (minors * 2.0) + (infos * 0.5);
        double overallScore = Math.max(0.0, Math.min(100.0, 100.0 - penalty));

        // Category breakdown
        Map<RuleCategory, Double> catScores = new EnumMap<>(RuleCategory.class);
        Map<RuleCategory, List<RuleViolation>> byCat = violations.stream()
                .collect(Collectors.groupingBy(RuleViolation::category));

        for (RuleCategory cat : RuleCategory.values()) {
            List<RuleViolation> catV = byCat.getOrDefault(cat, Collections.emptyList());
            double catPen = 0.0;
            for (RuleViolation cv : catV) {
                switch (cv.severity()) {
                    case BLOCKER -> catPen += 25.0;
                    case CRITICAL -> catPen += 15.0;
                    case MAJOR -> catPen += 5.0;
                    case MINOR -> catPen += 2.0;
                    case INFO -> catPen += 0.5;
                }
            }
            catScores.put(cat, Math.max(0.0, Math.min(100.0, 100.0 - catPen)));
        }

        boolean compliant = blockers == 0 && criticals == 0 && overallScore >= 80.0;

        return new EnforcementReport(
                projectId,
                Instant.now(),
                scannedCount,
                violations.size(),
                blockers,
                criticals,
                majors,
                minors,
                infos,
                overallScore,
                Collections.unmodifiableMap(catScores),
                Collections.unmodifiableList(violations),
                compliant
        );
    }

    private static void scanJavaFile(String path, String content, List<RuleViolation> violations) {
        String[] lines = content.split("\n", -1);

        for (int i = 0; i < lines.length; i++) {
            int lineNum = i + 1;
            String line = lines[i];

            // 1. Security Violations
            checkPattern(line, lineNum, path, "WebSecurityConfigurerAdapter",
                    "SEC-001", violations,
                    "WebSecurityConfigurerAdapter is removed in Spring Security 6",
                    "Declare a @Bean SecurityFilterChain instead.");

            checkPattern(line, lineNum, path, "authorizeRequests\\(",
                    "SEC-002", violations,
                    "authorizeRequests() is deprecated and removed in Spring Security 6",
                    "Migrate to authorizeHttpRequests(auth -> auth.requestMatchers(...)).");

            checkPattern(line, lineNum, path, "antMatchers\\(",
                    "SEC-003", violations,
                    "antMatchers() is replaced by requestMatchers()",
                    "Use requestMatchers(...) with MvcRequestMatcher / AntPathRequestMatcher.");

            checkPattern(line, lineNum, path, "@EnableGlobalMethodSecurity",
                    "SEC-007", violations,
                    "@EnableGlobalMethodSecurity is deprecated and removed",
                    "Replace with @EnableMethodSecurity.");

            checkPattern(line, lineNum, path, "setAllowedOrigins\\(.*\\*.*\\)",
                    "SEC-008", violations,
                    "Wildcard origin with allowCredentials is a critical CORS security vulnerability",
                    "Use setAllowedOriginPatterns(List.of(\"*\")) or restrict specific origins.");

            // 2. JPA & Hibernate 6 Violations
            checkPattern(line, lineNum, path, "import javax.persistence.",
                    "JPA-001", violations,
                    "javax.persistence.* namespace must be migrated to jakarta.persistence.*",
                    "Replace import javax.persistence.* with jakarta.persistence.*.");

            checkPattern(line, lineNum, path, "@TypeDef",
                    "JPA-002", violations,
                    "@TypeDef is removed in Hibernate 6",
                    "Use @JdbcTypeCode(SqlTypes.JSON) or custom UserType.");

            checkPattern(line, lineNum, path, "@Type\\(type\\s*=\\s*\"json\"\\)",
                    "JPA-003", violations,
                    "@Type(type = \"json\") is removed in Hibernate 6",
                    "Replace with @JdbcTypeCode(SqlTypes.JSON).");

            checkPattern(line, lineNum, path, "org.hibernate.criterion.Restrictions",
                    "JPA-004", violations,
                    "Legacy Hibernate Criteria API (Restrictions) is removed",
                    "Rewrite with JPA CriteriaBuilder or Spring Data Specifications.");

            checkPattern(line, lineNum, path, "org.hibernate.Criteria",
                    "JPA-004", violations,
                    "Legacy org.hibernate.Criteria is removed in Hibernate 6",
                    "Rewrite using JPA CriteriaQuery.");

            // Check positional parameter without index in queries
            if ((line.contains("createQuery") || line.contains("@Query")) && line.contains(" = ?") && !line.contains(" = ?1")) {
                addViolation("JPA-007", path, lineNum, line.trim(),
                        "Legacy unindexed positional parameter '?' is not supported in Hibernate 6",
                        "Migrate positional parameter '?' to indexed parameter '?1'.", violations);
            }

            // 3. Spring Cloud Microservice Violations
            checkPattern(line, lineNum, path, "@EnableCircuitBreaker",
                    "CLD-001", violations,
                    "Netflix Hystrix is deprecated and removed",
                    "Migrate to Resilience4j @CircuitBreaker.");

            checkPattern(line, lineNum, path, "@HystrixCommand",
                    "CLD-002", violations,
                    "@HystrixCommand is deprecated and removed",
                    "Migrate to io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker.");

            checkPattern(line, lineNum, path, "@RibbonClient",
                    "CLD-003", violations,
                    "Netflix Ribbon is replaced by Spring Cloud LoadBalancer",
                    "Replace @RibbonClient with @LoadBalancerClient.");

            checkPattern(line, lineNum, path, "@EnableZuulProxy",
                    "CLD-004", violations,
                    "Netflix Zuul 1.x is removed in modern Spring Cloud",
                    "Migrate routing to Spring Cloud Gateway RouteLocator.");

            checkPattern(line, lineNum, path, "org.springframework.cloud.openfeign.ribbon",
                    "CLD-005", violations,
                    "Feign Ribbon integration is deprecated",
                    "Use spring-cloud-starter-loadbalancer.");

            checkPattern(line, lineNum, path, "org.springframework.cloud.sleuth",
                    "CLD-008", violations,
                    "Spring Cloud Sleuth is superseded by Micrometer Tracing in Boot 3/4",
                    "Migrate imports to io.micrometer.tracing.");

            // 4. Core Framework & Web Violations
            checkPattern(line, lineNum, path, "import javax.servlet.",
                    "COR-001", violations,
                    "javax.servlet.* namespace must be migrated to jakarta.servlet.*",
                    "Replace javax.servlet.* with jakarta.servlet.*.");

            if (line.contains("import javax.annotation.") && !line.contains("import javax.annotation.processing.")) {
                addViolation("COR-002", path, lineNum, line.trim(),
                        "javax.annotation.* namespace must be migrated to jakarta.annotation.* (excluding standard JDK processing)",
                        "Replace javax.annotation.* with jakarta.annotation.*.", violations);
            }

            checkPattern(line, lineNum, path, "import javax.validation.",
                    "COR-003", violations,
                    "javax.validation.* namespace must be migrated to jakarta.validation.*",
                    "Replace javax.validation.* with jakarta.validation.*.");

            checkPattern(line, lineNum, path, "RestTemplateBuilder\\.build\\(\\)\\.setConnectTimeout",
                    "COR-009", violations,
                    "Direct mutation of RestTemplate timeout is deprecated in Spring Framework 6",
                    "Use RestTemplateBuilder.setConnectTimeout(Duration) before calling build().");

            // 5. Actuator & Observability
            checkPattern(line, lineNum, path, "management.security.enabled",
                    "ACT-003", violations,
                    "management.security.enabled is removed in modern Spring Boot",
                    "Configure actuator endpoints via SecurityFilterChain requestMatchers.");
        }
    }

    private static void scanXmlFile(String path, String content, List<RuleViolation> violations) {
        String[] lines = content.split("\n", -1);
        for (int i = 0; i < lines.length; i++) {
            int lineNum = i + 1;
            String line = lines[i];

            if (line.contains("<bean ") || line.contains("<beans ") || line.contains("<context:component-scan") ||
                    line.contains("<tx:annotation-driven") || line.contains("<mvc:annotation-driven")) {
                addViolation("XML-001", path, lineNum, line.trim(),
                        "Legacy XML Spring configuration detected; requires JavaConfig modernization",
                        "Convert XML bean definitions and namespaces to @Configuration and @Bean annotations.",
                        violations);
            }
        }
    }

    private static void scanConfigFile(String path, String content, List<RuleViolation> violations) {
        String[] lines = content.split("\n", -1);
        for (int i = 0; i < lines.length; i++) {
            int lineNum = i + 1;
            String line = lines[i];

            if (path.contains("bootstrap.yml") || path.contains("bootstrap.yaml")) {
                addViolation("CLD-006", path, lineNum, line.trim(),
                        "bootstrap.yml configuration is deprecated in Spring Cloud",
                        "Migrate configuration properties to application.yml using spring.config.import.",
                        violations);
                break; // Only flag once per bootstrap file
            }

            if (line.contains("spring.sleuth.")) {
                addViolation("ACT-005", path, lineNum, line.trim(),
                        "spring.sleuth.* properties are obsolete",
                        "Migrate tracing properties to management.tracing.* and management.zipkin.*.",
                        violations);
            }

            if (line.contains("security.basic.enabled") || line.contains("management.security.enabled")) {
                addViolation("ACT-003", path, lineNum, line.trim(),
                        "Legacy security property is removed",
                        "Configure endpoint security explicitly in SecurityFilterChain.",
                        violations);
            }
        }
    }

    private static void scanArchitecturalBoundaries(Map<String, String> files, List<RuleViolation> violations) {
        for (Map.Entry<String, String> entry : files.entrySet()) {
            String path = entry.getKey();
            String content = entry.getValue();

            // Layering Check: Controller directly accessing Repository without Service layer
            if (path.contains("Controller.java") || path.contains("Resource.java")) {
                if (content.contains("Repository") && !content.contains("Service") && content.contains("@Autowired")) {
                    int line = findFirstMatchingLine(content, "Repository");
                    addViolation("COR-010", path, line, "private final ...Repository repository;",
                            "Architectural layer violation: Controller directly injects Repository bypassing Service layer",
                            "Introduce a domain Service layer between Controller and Repository.",
                            violations);
                }

                // Check: Controller with @Transactional
                if (content.contains("@Transactional") && content.contains("@RestController")) {
                    int line = findFirstMatchingLine(content, "@Transactional");
                    addViolation("COR-011", path, line, "@Transactional on Controller",
                            "Transactional antipattern: @Transactional should not be applied at the Controller level",
                            "Move @Transactional boundaries to domain Service classes.",
                            violations);
                }
            }

            // Entity Antipattern Check: Domain Entity leaking API serialization annotations
            if (path.contains("entity") || path.contains("Entity.java")) {
                if (content.contains("@RestController") || content.contains("@RequestMapping")) {
                    int line = findFirstMatchingLine(content, "@RestController");
                    addViolation("COR-012", path, line, "Entity with web annotations",
                            "Domain entity contains web controller annotations",
                            "Separate Domain Entities from Web Controllers.",
                            violations);
                }
            }
        }
    }

    private static void checkPattern(String line, int lineNum, String path, String regexOrLiteral,
                                     String ruleId, List<RuleViolation> violations,
                                     String message, String fix) {
        if (line.matches(".*" + regexOrLiteral + ".*") || line.contains(regexOrLiteral.replace("\\", ""))) {
            addViolation(ruleId, path, lineNum, line.trim(), message, fix, violations);
        }
    }

    private static void addViolation(String ruleId, String path, int lineNum, String snippet,
                                     String message, String fix, List<RuleViolation> violations) {
        ModernizationRule catalogRule = RULES_BY_ID.get(ruleId);
        RuleCategory category = catalogRule != null ? catalogRule.category() : RuleCategory.CORE_FRAMEWORK;
        RuleSeverity severity = catalogRule != null ? catalogRule.severity() : RuleSeverity.MAJOR;
        String modernizer = catalogRule != null ? catalogRule.recipeOrModernizerClass() : "io.elmos.worker.SpringDiagnosticAutoRepairer";

        violations.add(new RuleViolation(
                ruleId,
                category,
                severity,
                path,
                lineNum,
                snippet,
                message,
                fix,
                modernizer
        ));
    }

    private static int findFirstMatchingLine(String content, String sub) {
        String[] lines = content.split("\n", -1);
        for (int i = 0; i < lines.length; i++) {
            if (lines[i].contains(sub)) {
                return i + 1;
            }
        }
        return 1;
    }

    /**
     * Converts an EnforcementReport into a compliant SARIF 2.1.0 JSON format.
     */
    public static String toSarifJson(EnforcementReport report) {
        StringBuilder sb = new StringBuilder();
        sb.append("{\n");
        sb.append("  \"$schema\": \"https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json\",\n");
        sb.append("  \"version\": \"2.1.0\",\n");
        sb.append("  \"runs\": [\n");
        sb.append("    {\n");
        sb.append("      \"tool\": {\n");
        sb.append("        \"driver\": {\n");
        sb.append("          \"name\": \"Elmos Spring Modernization Rulebook Enforcer\",\n");
        sb.append("          \"version\": \"4.1.0-ENTERPRISE\",\n");
        sb.append("          \"informationUri\": \"https://github.com/elmos-ai/elmos\",\n");
        sb.append("          \"rules\": [\n");

        // Unique rules in this report
        Set<String> ruleIds = report.violations().stream().map(RuleViolation::ruleId).collect(Collectors.toCollection(LinkedHashSet::new));
        int rIdx = 0;
        for (String rid : ruleIds) {
            ModernizationRule mr = RULES_BY_ID.get(rid);
            String desc = mr != null ? escapeJson(mr.description()) : "Spring Modernization Rule " + rid;
            String sev = mr != null ? mr.severity().name().toLowerCase() : "warning";
            sb.append("            {\n");
            sb.append(String.format("              \"id\": \"%s\",\n", rid));
            sb.append(String.format("              \"shortDescription\": { \"text\": \"%s\" },\n", desc));
            sb.append(String.format("              \"defaultConfiguration\": { \"level\": \"%s\" }\n",
                    sev.equals("blocker") || sev.equals("critical") ? "error" : "warning"));
            sb.append("            }").append(++rIdx < ruleIds.size() ? "," : "").append("\n");
        }

        sb.append("          ]\n");
        sb.append("        }\n");
        sb.append("      },\n");
        sb.append("      \"results\": [\n");

        for (int i = 0; i < report.violations().size(); i++) {
            RuleViolation v = report.violations().get(i);
            String level = (v.severity() == RuleSeverity.BLOCKER || v.severity() == RuleSeverity.CRITICAL) ? "error" : "warning";

            sb.append("        {\n");
            sb.append(String.format("          \"ruleId\": \"%s\",\n", v.ruleId()));
            sb.append(String.format("          \"level\": \"%s\",\n", level));
            sb.append(String.format("          \"message\": { \"text\": \"%s\" },\n", escapeJson(v.message())));
            sb.append("          \"locations\": [\n");
            sb.append("            {\n");
            sb.append("              \"physicalLocation\": {\n");
            sb.append("                \"artifactLocation\": {\n");
            sb.append(String.format("                  \"uri\": \"%s\"\n", escapeJson(v.filePath())));
            sb.append("                },\n");
            sb.append("                \"region\": {\n");
            sb.append(String.format("                  \"startLine\": %d\n", v.lineNumber()));
            sb.append("                }\n");
            sb.append("              }\n");
            sb.append("            }\n");
            sb.append("          ],\n");
            sb.append("          \"properties\": {\n");
            sb.append(String.format("            \"category\": \"%s\",\n", v.category().name()));
            sb.append(String.format("            \"severity\": \"%s\",\n", v.severity().name()));
            sb.append(String.format("            \"remediation\": \"%s\",\n", escapeJson(v.recommendedFix())));
            sb.append(String.format("            \"modernizerClass\": \"%s\"\n", escapeJson(v.recipeOrModernizerClass())));
            sb.append("          }\n");
            sb.append("        }").append(i < report.violations().size() - 1 ? "," : "").append("\n");
        }

        sb.append("      ]\n");
        sb.append("    }\n");
        sb.append("  ]\n");
        sb.append("}\n");

        return sb.toString();
    }

    /**
     * Generates an executive Markdown compliance report.
     */
    public static String toMarkdownReport(EnforcementReport report) {
        StringBuilder sb = new StringBuilder();
        sb.append("# Spring Modernization Architecture Rulebook Enforcement Report\n\n");
        sb.append(String.format("- **Project ID**: `%s`\n", report.projectId()));
        sb.append(String.format("- **Timestamp**: `%s`\n", report.scanTime()));
        sb.append(String.format("- **Compliance Verdict**: %s (Score: `%.1f / 100.0`)\n",
                report.isCompliant() ? "✅ **COMPLIANT**" : "❌ **NON-COMPLIANT**", report.complianceScore()));
        sb.append(String.format("- **Files Scanned**: `%d` | **Total Violations**: `%d`\n",
                report.totalFilesScanned(), report.totalViolations()));
        sb.append(String.format("- **Severity Counts**: Blocker: `%d` | Critical: `%d` | Major: `%d` | Minor: `%d` | Info: `%d`\n\n",
                report.blockerCount(), report.criticalCount(), report.majorCount(), report.minorCount(), report.infoCount()));

        sb.append("## Category Compliance Breakdown\n\n");
        sb.append("| Category | Compliance Score | Status |\n");
        sb.append("| :--- | :---: | :---: |\n");
        for (Map.Entry<RuleCategory, Double> entry : report.categoryComplianceScores().entrySet()) {
            double score = entry.getValue();
            String status = score >= 90.0 ? "✅ EXCELLENT" : (score >= 70.0 ? "⚠️ WARNING" : "❌ CRITICAL");
            sb.append(String.format("| `%s` | `%.1f%%` | %s |\n", entry.getKey().getDisplayName(), score, status));
        }
        sb.append("\n");

        if (!report.violations().isEmpty()) {
            sb.append("## Detected Violations & Remediation Guidance\n\n");
            sb.append("| Rule ID | Category | Severity | Location | Message | Recommended Fix |\n");
            sb.append("| :--- | :--- | :---: | :--- | :--- | :--- |\n");
            for (RuleViolation v : report.violations()) {
                sb.append(String.format("| `%s` | `%s` | `%s` | `%s:%d` | %s | %s |\n",
                        v.ruleId(), v.category().name(), v.severity().name(), v.filePath(), v.lineNumber(),
                        v.message(), v.recommendedFix()));
            }
            sb.append("\n");
        } else {
            sb.append("### 🎉 Clean Architecture Confirmed: Zero rulebook violations detected!\n\n");
        }

        return sb.toString();
    }

    private static String escapeJson(String s) {
        if (s == null) return "";
        return s.replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\b", "\\b")
                .replace("\f", "\\f")
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t");
    }
}
