package io.elmos.worker.datasource;

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
import java.util.stream.Stream;

/**
 * Industrial-grade modernizer for JDBC Connection Pools (Druid to Druid-Spring-Boot-3 / HikariCP)
 * and JDBC Driver class name and URL parameter normalization.
 *
 * <p>Key challenges in enterprise Spring Boot 3 database connectivity:
 * <ol>
 *   <li><b>Legacy Druid starter incompatibility:</b> Old {@code druid-spring-boot-starter} 1.1.x/1.2.x
 *       references {@code javax.servlet.Filter}, throwing {@code NoClassDefFoundError} on Spring Boot 3 startup.
 *       This modernizer upgrades to {@code druid-spring-boot-3-starter} 1.2.23+.</li>
 *   <li><b>Deprecated MySQL Driver:</b> {@code com.mysql.jdbc.Driver} is deprecated in favor of
 *       {@code com.mysql.cj.jdbc.Driver}.</li>
 *   <li><b>Missing MySQL 8+ URL Parameters:</b> MySQL 8+ connections require {@code serverTimezone=Asia/Shanghai}
 *       and {@code allowPublicKeyRetrieval=true} to prevent handshake failure and 8-hour timezone drift.</li>
 *   <li><b>Oracle Driver Upgrade:</b> Replaces legacy {@code ojdbc6}/{@code ojdbc7} with {@code ojdbc11}.</li>
 * </ol>
 */
public final class SpringDatasourcePoolAndDriverModernizer {

    public record DatasourcePoolModernizationResult(
            boolean modified,
            int changesCount,
            Set<String> modifiedFiles,
            List<String> rulesApplied,
            List<String> warnings
    ) {
        public static DatasourcePoolModernizationResult empty() {
            return new DatasourcePoolModernizationResult(false, 0, Collections.emptySet(), Collections.emptyList(), Collections.emptyList());
        }
    }

    private static final Pattern OLD_DRUID_DEP_PATTERN = Pattern.compile("(?s)<dependency>\\s*<groupId>com\\.alibaba</groupId>\\s*<artifactId>druid-spring-boot-starter</artifactId>\\s*(?:<version>[^<]+</version>\\s*)?</dependency>");
    private static final Pattern OLD_OJDBC_DEP_PATTERN = Pattern.compile("(?s)<dependency>\\s*<groupId>[^<]+</groupId>\\s*<artifactId>ojdbc[678]</artifactId>\\s*(?:<version>[^<]+</version>\\s*)?</dependency>");

    private SpringDatasourcePoolAndDriverModernizer() {}

    public static DatasourcePoolModernizationResult modernize(Path projectRoot) {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        if (!Files.isDirectory(projectRoot)) {
            return DatasourcePoolModernizationResult.empty();
        }

        Set<String> modifiedFiles = new LinkedHashSet<>();
        List<String> rulesApplied = new ArrayList<>();
        List<String> warnings = new ArrayList<>();
        int changes = 0;

        // 1. Modernize pom.xml dependencies
        Path pomFile = projectRoot.resolve("pom.xml");
        if (Files.isRegularFile(pomFile)) {
            try {
                String pomContent = Files.readString(pomFile, StandardCharsets.UTF_8);
                String updated = pomContent;

                if (OLD_DRUID_DEP_PATTERN.matcher(updated).find()) {
                    String druid3Dep = """
                                <dependency>
                                  <groupId>com.alibaba</groupId>
                                  <artifactId>druid-spring-boot-3-starter</artifactId>
                                  <version>1.2.23</version>
                                </dependency>""";
                    updated = OLD_DRUID_DEP_PATTERN.matcher(updated).replaceAll(Matcher.quoteReplacement(druid3Dep));
                    rulesApplied.add("DRUID_UPGRADED_TO_DRUID_SPRING_BOOT_3_STARTER");
                    changes++;
                }

                if (OLD_OJDBC_DEP_PATTERN.matcher(updated).find()) {
                    String ojdbc11Dep = """
                                <dependency>
                                  <groupId>com.oracle.database.jdbc</groupId>
                                  <artifactId>ojdbc11</artifactId>
                                  <version>23.4.0.24.05</version>
                                </dependency>""";
                    updated = OLD_OJDBC_DEP_PATTERN.matcher(updated).replaceAll(Matcher.quoteReplacement(ojdbc11Dep));
                    rulesApplied.add("ORACLE_DRIVER_UPGRADED_TO_OJDBC11");
                    changes++;
                }

                if (!updated.equals(pomContent)) {
                    Files.writeString(pomFile, updated, StandardCharsets.UTF_8);
                    modifiedFiles.add(projectRoot.relativize(pomFile).toString());
                }
            } catch (IOException e) {
                warnings.add("Failed to modernize pom.xml: " + e.getMessage());
            }
        }

        // 2. Modernize Application Configuration files (Driver class name & URL params)
        ConfigModernizationResult cfgRes = modernizeConfigs(projectRoot);
        if (cfgRes.modified()) {
            modifiedFiles.addAll(cfgRes.files());
            rulesApplied.addAll(cfgRes.rules());
            changes += cfgRes.changes();
        }

        return new DatasourcePoolModernizationResult(!modifiedFiles.isEmpty(), changes, modifiedFiles, rulesApplied, warnings);
    }

    private record ConfigModernizationResult(boolean modified, int changes, Set<String> files, List<String> rules) {}

    private static ConfigModernizationResult modernizeConfigs(Path projectRoot) {
        Set<String> files = new LinkedHashSet<>();
        List<String> rules = new ArrayList<>();
        int changes = 0;

        try (Stream<Path> stream = Files.walk(projectRoot)) {
            List<Path> configs = stream
                    .filter(Files::isRegularFile)
                    .filter(p -> {
                        String name = p.getFileName().toString();
                        return (name.startsWith("application.") || name.startsWith("application-")) &&
                                (name.endsWith(".yml") || name.endsWith(".yaml") || name.endsWith(".properties"));
                    })
                    .toList();

            for (Path config : configs) {
                try {
                    String content = Files.readString(config, StandardCharsets.UTF_8);
                    String updated = content;

                    // 1. Modernize MySQL Driver Class Name
                    if (updated.contains("com.mysql.jdbc.Driver")) {
                        updated = updated.replace("com.mysql.jdbc.Driver", "com.mysql.cj.jdbc.Driver");
                        rules.add("MYSQL_DRIVER_CLASS_UPGRADED_TO_CJ");
                        changes++;
                    }

                    // 2. Modernize JDBC MySQL URL parameters
                    if (updated.contains("jdbc:mysql://")) {
                        Pattern urlPattern = Pattern.compile("(jdbc:mysql://[a-zA-Z0-9._\\-:]+/[a-zA-Z0-9_\\-]+)(\\?[^\r\n\"']*)?");
                        Matcher matcher = urlPattern.matcher(updated);
                        if (matcher.find()) {
                            String baseUrl = matcher.group(1);
                            String queryParams = matcher.group(2);
                            String normalizedQuery = normalizeMysqlQueryParams(queryParams);
                            String replacement = baseUrl + normalizedQuery;
                            updated = matcher.replaceFirst(Matcher.quoteReplacement(replacement));
                            rules.add("MYSQL_JDBC_URL_PARAMETERS_NORMALIZED");
                            changes++;
                        }
                    }

                    if (!updated.equals(content)) {
                        Files.writeString(config, updated, StandardCharsets.UTF_8);
                        files.add(projectRoot.relativize(config).toString());
                    }
                } catch (IOException ignored) {}
            }
        } catch (IOException ignored) {}

        return new ConfigModernizationResult(!files.isEmpty(), changes, files, rules);
    }

    private static String normalizeMysqlQueryParams(String existingQuery) {
        if (existingQuery == null || existingQuery.trim().isEmpty() || existingQuery.equals("?")) {
            return "?serverTimezone=Asia/Shanghai&allowPublicKeyRetrieval=true&useSSL=false";
        }

        String raw = existingQuery.startsWith("?") ? existingQuery.substring(1) : existingQuery;
        // Clean out legacy parameters
        raw = raw.replace("useUnicode=true&", "").replace("&useUnicode=true", "").replace("useUnicode=true", "");
        raw = raw.replace("characterEncoding=utf-8&", "").replace("&characterEncoding=utf-8", "").replace("characterEncoding=utf-8", "");
        raw = raw.replace("characterEncoding=UTF-8&", "").replace("&characterEncoding=UTF-8", "").replace("characterEncoding=UTF-8", "");

        StringBuilder sb = new StringBuilder("?");
        sb.append(raw);
        if (!raw.isEmpty() && !raw.endsWith("&")) {
            sb.append("&");
        }
        if (!raw.contains("serverTimezone")) {
            sb.append("serverTimezone=Asia/Shanghai&");
        }
        if (!raw.contains("allowPublicKeyRetrieval")) {
            sb.append("allowPublicKeyRetrieval=true&");
        }
        if (!raw.contains("useSSL")) {
            sb.append("useSSL=false&");
        }

        String res = sb.toString();
        if (res.endsWith("&")) {
            res = res.substring(0, res.length() - 1);
        }
        return res;
    }
}
