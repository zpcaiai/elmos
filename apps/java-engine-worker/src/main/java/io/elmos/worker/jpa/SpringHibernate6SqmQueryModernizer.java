package io.elmos.worker.jpa;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Hibernate 6 SQM (Semantic Query Model) & Naming Strategy Modernizer.
 *
 * <p>Modernizes persistence code for Hibernate 6.x / Spring Boot 3.x:
 * <ol>
 *   <li><b>SQM Strict Query Validation:</b>
 *       Validates that Spring Data JPA {@code @Query} HQL queries conform to strict SQM rules:
 *       eliminates unindexed {@code ?} positional parameters (converted to {@code ?1}, {@code ?2}),
 *       and flags queries missing {@code @Modifying} on UPDATE/DELETE statements.</li>
 *   <li><b>Hibernate 6 Type Model Modernization:</b>
 *       Converts legacy {@code @Type(type = "json" | "jsonb")} annotations to
 *       {@code @JdbcTypeCode(SqlTypes.JSON)}, updating imports to
 *       {@code org.hibernate.annotations.JdbcTypeCode} and {@code org.hibernate.type.SqlTypes}.</li>
 *   <li><b>Naming Strategy Freezing:</b>
 *       Locks physical and implicit naming strategies in {@code application.yml} to
 *       {@code org.hibernate.boot.model.naming.CamelCaseToUnderscoresNamingStrategy}
 *       and {@code org.springframework.boot.orm.jpa.hibernate.SpringImplicitNamingStrategy}
 *       to prevent catastrophic database table/column name drift during upgrade.</li>
 * </ol>
 */
public final class SpringHibernate6SqmQueryModernizer {

    public record SqmModernizationResult(
            boolean modified,
            int changesCount,
            Set<String> modifiedFiles,
            List<String> rulesApplied,
            List<String> warnings
    ) {
        public static SqmModernizationResult empty() {
            return new SqmModernizationResult(false, 0, Collections.emptySet(), Collections.emptyList(), Collections.emptyList());
        }
    }

    private static final Pattern LEGACY_TYPE_JSON = Pattern.compile(
            "@Type\\s*\\(\\s*(?:type\\s*=\\s*)?\"(?:json|jsonb)\"\\s*\\)"
    );

    private static final Pattern LEGACY_TYPE_IMPORT = Pattern.compile(
            "import\\s+org\\.hibernate\\.annotations\\.Type;"
    );

    private static final Pattern LEGACY_TYPEDEF_IMPORT = Pattern.compile(
            "import\\s+org\\.hibernate\\.annotations\\.TypeDef(?:s)?;"
    );

    private static final Pattern LEGACY_TYPEDEF = Pattern.compile(
            "@TypeDef(?:s)?\\s*\\([\\s\\S]*?\\)"
    );

    private static final Pattern UNINDEXED_PARAM_IN_QUERY = Pattern.compile(
            "(@Query\\s*\\([^)]*\"[^\"]*)\\?(?!\\d+)([^)]*\\))"
    );

    private static final Pattern DML_QUERY_WITHOUT_MODIFYING = Pattern.compile(
            "(?<!@Modifying\\s*)@Query\\s*\\(\\s*\"\\s*(?:UPDATE|DELETE)\\s+[^)]+\\)"
    );

    public SqmModernizationResult modernize(Path projectRoot) throws IOException {
        return modernize(projectRoot, true);
    }

    /**
     * Executes complete Hibernate 6 SQM and naming strategy modernization across the workspace.
     */
    public SqmModernizationResult modernize(Path projectRoot, boolean updateYml) throws IOException {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        if (!Files.isDirectory(projectRoot)) {
            return SqmModernizationResult.empty();
        }

        boolean anyModified = false;
        int totalChanges = 0;
        Set<String> modifiedFiles = new LinkedHashSet<>();
        List<String> rulesApplied = new ArrayList<>();
        List<String> warnings = new ArrayList<>();

        // 1. Scan Java files for @Type and @Query SQM requirements
        try (var stream = Files.walk(projectRoot)) {
            List<Path> javaFiles = stream
                    .filter(Files::isRegularFile)
                    .filter(p -> p.toString().endsWith(".java"))
                    .toList();

            for (Path javaFile : javaFiles) {
                String source = Files.readString(javaFile, StandardCharsets.UTF_8);
                boolean fileChanged = false;

                // A. Replace @Type(type = "json" | "jsonb") with @JdbcTypeCode(SqlTypes.JSON)
                Matcher typeJsonMatcher = LEGACY_TYPE_JSON.matcher(source);
                if (typeJsonMatcher.find()) {
                    source = typeJsonMatcher.replaceAll("@JdbcTypeCode(SqlTypes.JSON)");
                    fileChanged = true;
                    totalChanges++;
                    rulesApplied.add("REPLACE_LEGACY_TYPE_WITH_JDBCTYPECODE_JSON");

                    // Ensure required imports exist
                    if (!source.contains("org.hibernate.annotations.JdbcTypeCode")) {
                        source = "import org.hibernate.annotations.JdbcTypeCode;\n"
                                + "import org.hibernate.type.SqlTypes;\n"
                                + source;
                    }
                }

                // Strip legacy @TypeDef / @TypeDefs annotations and imports
                Matcher typeDefMatcher = LEGACY_TYPEDEF.matcher(source);
                if (typeDefMatcher.find()) {
                    source = typeDefMatcher.replaceAll("");
                    fileChanged = true;
                    totalChanges++;
                    rulesApplied.add("STRIP_DEPRECATED_HIBERNATE_TYPEDEF");
                }

                // Remove legacy @Type and @TypeDef imports
                Matcher typeImportMatcher = LEGACY_TYPE_IMPORT.matcher(source);
                if (typeImportMatcher.find()) {
                    source = typeImportMatcher.replaceAll("// [ELMOS-CLEANUP] Deprecated Hibernate 5 @Type import removed");
                    fileChanged = true;
                    totalChanges++;
                }

                Matcher typeDefImportMatcher = LEGACY_TYPEDEF_IMPORT.matcher(source);
                if (typeDefImportMatcher.find()) {
                    source = typeDefImportMatcher.replaceAll("// [ELMOS-CLEANUP] Deprecated Hibernate 5 @TypeDef removed");
                    fileChanged = true;
                    totalChanges++;
                }

                // B. SQM Unindexed parameter fix: convert ? to ?1 in @Query
                Matcher unindexedMatcher = UNINDEXED_PARAM_IN_QUERY.matcher(source);
                if (unindexedMatcher.find()) {
                    source = unindexedMatcher.replaceAll("$1?1$2");
                    fileChanged = true;
                    totalChanges++;
                    rulesApplied.add("REPLACE_UNINDEXED_POSITIONAL_PARAM_IN_QUERY");
                }

                // C. SQM Warning for DML queries missing @Modifying
                Matcher dmlMatcher = DML_QUERY_WITHOUT_MODIFYING.matcher(source);
                if (dmlMatcher.find()) {
                    warnings.add(javaFile.getFileName() + ": Detected UPDATE/DELETE @Query without @Modifying annotation; SQM requires @Modifying for DML execution.");
                }

                if (fileChanged) {
                    Files.writeString(javaFile, source, StandardCharsets.UTF_8);
                    anyModified = true;
                    modifiedFiles.add(projectRoot.relativize(javaFile).toString().replace('\\', '/'));
                }
            }
        }

        // 2. Lock Naming Strategy in application.yml to prevent table/column name drift if requested
        if (updateYml) {
            Path ymlPath = projectRoot.resolve("src/main/resources/application.yml");
            if (Files.isRegularFile(ymlPath)) {
                String ymlContent = Files.readString(ymlPath, StandardCharsets.UTF_8);
                if (!ymlContent.contains("physical-strategy:")) {
                    String namingConfig =
                            """

                            spring:
                              jpa:
                                hibernate:
                                  naming:
                                    physical-strategy: org.hibernate.boot.model.naming.CamelCaseToUnderscoresNamingStrategy
                                    implicit-strategy: org.springframework.boot.orm.jpa.hibernate.SpringImplicitNamingStrategy
                            """;
                    Files.writeString(ymlPath, ymlContent + namingConfig, StandardCharsets.UTF_8);
                    anyModified = true;
                    totalChanges++;
                    modifiedFiles.add(projectRoot.relativize(ymlPath).toString().replace('\\', '/'));
                    rulesApplied.add("FREEZE_HIBERNATE_6_NAMING_STRATEGY");
                }
            }
        }

        return new SqmModernizationResult(anyModified, totalChanges, modifiedFiles, rulesApplied, warnings);
    }
}
