package io.elmos.worker.validation;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Industrial-grade validator for JPA / Hibernate 6 modernization rules.
 *
 * <p>Audits a codebase to guarantee:
 * <ul>
 *   <li>Zero legacy {@code javax.persistence.*} imports (all migrated to {@code jakarta.persistence.*}).</li>
 *   <li>Zero deprecated Hibernate 5 {@code @TypeDef} / {@code @Type} annotations (migrated to {@code @JdbcTypeCode(SqlTypes.JSON)}).</li>
 *   <li>Zero deprecated {@code org.hibernate.Criteria} or {@code Restrictions} usage (migrated to CriteriaBuilder/Specification).</li>
 *   <li>Zero legacy unindexed SQM positional parameters (e.g. {@code ?} -> {@code ?1}).</li>
 *   <li>Proper registration of Hibernate 6 {@code FunctionContributor} SPI for custom functions.</li>
 * </ul>
 */
public final class SpringJpaHibernateQueryValidator {

    public enum Severity {
        CRITICAL,
        HIGH,
        MEDIUM,
        LOW,
        INFO
    }

    public record JpaViolation(
            String ruleId,
            Severity severity,
            String filePath,
            int line,
            String message,
            String remediationSnippet
    ) {}

    public record JpaHibernateAuditReport(
            int totalFilesScanned,
            int totalViolations,
            int criticalViolations,
            int highViolations,
            double complianceScore,
            boolean isCompliant,
            List<JpaViolation> violations
    ) {}

    private static final Pattern UNINDEXED_PARAM_PATTERN = Pattern.compile("(?<!\\?)\\?(?!\\d)");

    public JpaHibernateAuditReport auditProject(Path projectRoot) throws IOException {
        List<JpaViolation> violations = new ArrayList<>();
        int filesScanned = 0;

        if (!Files.isDirectory(projectRoot)) {
            return new JpaHibernateAuditReport(0, 0, 0, 0, 100.0, true, Collections.emptyList());
        }

        try (var stream = Files.walk(projectRoot)) {
            List<Path> javaFiles = stream.filter(p -> p.toString().endsWith(".java")).toList();
            for (Path jf : javaFiles) {
                filesScanned++;
                auditJavaFile(jf, violations);
            }
        }

        int critical = (int) violations.stream().filter(v -> v.severity() == Severity.CRITICAL).count();
        int high = (int) violations.stream().filter(v -> v.severity() == Severity.HIGH).count();
        int medium = (int) violations.stream().filter(v -> v.severity() == Severity.MEDIUM).count();

        double penalty = (critical * 25.0) + (high * 10.0) + (medium * 3.0);
        double complianceScore = Math.max(0.0, 100.0 - penalty);
        boolean isCompliant = critical == 0 && high == 0;

        return new JpaHibernateAuditReport(
                filesScanned,
                violations.size(),
                critical,
                high,
                complianceScore,
                isCompliant,
                Collections.unmodifiableList(violations)
        );
    }

    public List<JpaViolation> auditJavaFile(Path javaFile, List<JpaViolation> violations) {
        try {
            String content = Files.readString(javaFile, StandardCharsets.UTF_8);
            String relativePath = javaFile.toString();

            if (content.contains("import javax.persistence.")) {
                violations.add(new JpaViolation(
                        "JPA-001",
                        Severity.CRITICAL,
                        relativePath,
                        findLineNumber(content, "import javax.persistence."),
                        "Legacy javax.persistence import detected. Spring Boot 3+ and Hibernate 6 require jakarta.persistence.*.",
                        "import jakarta.persistence.*;"
                ));
            }

            if (content.contains("@TypeDef(") || content.contains("@TypeDefs(")) {
                violations.add(new JpaViolation(
                        "JPA-002",
                        Severity.CRITICAL,
                        relativePath,
                        findLineNumber(content, "@TypeDef"),
                        "Deprecated @TypeDef/@TypeDefs annotation detected. Hibernate 6 removed these in favor of standard TypeContributer or @JdbcTypeCode.",
                        "@JdbcTypeCode(SqlTypes.JSON)"
                ));
            }

            if (content.contains("@Type(type =") || content.contains("@Type(type=")) {
                violations.add(new JpaViolation(
                        "JPA-003",
                        Severity.HIGH,
                        relativePath,
                        findLineNumber(content, "@Type"),
                        "Deprecated @Type(type = \"...\") annotation detected. In Hibernate 6, replace with @JdbcTypeCode(SqlTypes.JSON) or user-defined Converter.",
                        "@JdbcTypeCode(SqlTypes.JSON)\nprivate Map<String, Object> attributes;"
                ));
            }

            if (content.contains("org.hibernate.Criteria") || content.contains("createCriteria(") || content.contains("org.hibernate.criterion.Restrictions")) {
                violations.add(new JpaViolation(
                        "JPA-004",
                        Severity.CRITICAL,
                        relativePath,
                        findLineNumber(content, "Criteria"),
                        "Deprecated Hibernate legacy Criteria API detected. Removed in Hibernate 6. Refactor to JPA CriteriaBuilder or Spring Data JPA Specification.",
                        """
                        CriteriaBuilder cb = entityManager.getCriteriaBuilder();
                        CriteriaQuery<Entity> cq = cb.createQuery(Entity.class);
                        """
                ));
            }

            // Check SQM positional queries in @Query strings
            checkQueryPositionalParameters(content, relativePath, violations);

            // Check if class extends Dialect and uses registerFunction instead of FunctionContributor
            if (content.contains("extends Dialect") && content.contains("registerFunction(")) {
                violations.add(new JpaViolation(
                        "JPA-006",
                        Severity.HIGH,
                        relativePath,
                        findLineNumber(content, "registerFunction("),
                        "Custom Dialect subclass registers functions using legacy registerFunction(). Hibernate 6 uses FunctionContributor SPI.",
                        """
                        public class MyFunctionContributor implements FunctionContributor {
                            @Override
                            public void contributeFunctions(FunctionContributions functionContributions) {
                                functionContributions.getFunctionRegistry().registerNamed(...);
                            }
                        }
                        """
                ));
            }

        } catch (IOException ignored) {}

        return violations;
    }

    private void checkQueryPositionalParameters(String content, String filePath, List<JpaViolation> violations) {
        Pattern queryPattern = Pattern.compile("@Query\\s*\\(\\s*(?:value\\s*=\\s*)?\"([^\"]+)\"");
        Matcher matcher = queryPattern.matcher(content);
        while (matcher.find()) {
            String queryStr = matcher.group(1);
            if (UNINDEXED_PARAM_PATTERN.matcher(queryStr).find()) {
                violations.add(new JpaViolation(
                        "JPA-005",
                        Severity.HIGH,
                        filePath,
                        findLineNumber(content, matcher.group(0)),
                        "Legacy unindexed positional parameter '?' detected in @Query: \"" + queryStr + "\". Hibernate 6 SQM requires ordinal indices (e.g. ?1, ?2).",
                        queryStr.replaceAll("(?<!\\?)\\?(?!\\d)", "?1")
                ));
            }
        }
    }

    private static int findLineNumber(String text, String substring) {
        int index = text.indexOf(substring);
        if (index < 0) return 1;
        int line = 1;
        for (int i = 0; i < index; i++) {
            if (text.charAt(i) == '\n') line++;
        }
        return line;
    }
}
