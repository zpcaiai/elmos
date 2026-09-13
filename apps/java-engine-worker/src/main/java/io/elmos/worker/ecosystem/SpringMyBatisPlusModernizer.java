package io.elmos.worker.ecosystem;

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
 * Exact Spring Boot 3 / MyBatis-Plus migration operator.
 *
 * <p>The dependency edge is pinned to MyBatis-Plus 3.5.17. Pagination and tenant plugins are
 * deliberately not guessed: the operator rewrites only configurations whose database type and
 * tenant expression can be recovered. Ambiguous plugins are returned as blocking obligations.
 */
public final class SpringMyBatisPlusModernizer {
    static final String TARGET_VERSION = "3.5.17";

    public record ModernizationResult(
            boolean modified,
            Set<String> modifiedFiles,
            List<String> rulesApplied,
            List<String> blockingObligations
    ) {
        static ModernizationResult empty() {
            return new ModernizationResult(false, Set.of(), List.of(), List.of());
        }
    }

    private static final Pattern DEPENDENCY = Pattern.compile(
            "(?s)(<dependency>\\s*<groupId>com\\.baomidou</groupId>\\s*<artifactId>)"
                    + "mybatis-plus-boot-starter(</artifactId>)"
                    + "((?:(?!</dependency>).)*?)(</dependency>)");
    private static final Pattern VERSION = Pattern.compile("<version>[^<]+</version>");
    private static final Pattern DB_TYPE = Pattern.compile("DbType\\.([A-Z0-9_]+)");

    private SpringMyBatisPlusModernizer() {}

    public static ModernizationResult modernize(Path projectRoot) {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        if (!Files.isDirectory(projectRoot)) {
            return ModernizationResult.empty();
        }
        Set<String> modified = new LinkedHashSet<>();
        List<String> rules = new ArrayList<>();
        List<String> blockers = new ArrayList<>();
        try (var files = Files.walk(projectRoot)) {
            for (Path file : files.filter(Files::isRegularFile).toList()) {
                String name = file.getFileName().toString();
                if (name.equals("pom.xml")) {
                    rewritePom(projectRoot, file, modified, rules);
                } else if (name.endsWith(".java")) {
                    rewritePluginConfiguration(projectRoot, file, modified, rules, blockers);
                }
            }
        } catch (IOException e) {
            blockers.add("IO:" + e.getClass().getSimpleName());
        }
        return new ModernizationResult(!modified.isEmpty(), Collections.unmodifiableSet(modified),
                List.copyOf(rules), List.copyOf(blockers));
    }

    private static void rewritePom(Path root, Path pom, Set<String> modified, List<String> rules)
            throws IOException {
        String before = Files.readString(pom, StandardCharsets.UTF_8);
        Matcher matcher = DEPENDENCY.matcher(before);
        StringBuffer output = new StringBuffer();
        boolean changed = false;
        while (matcher.find()) {
            String body = matcher.group(3);
            String normalized = VERSION.matcher(body).replaceFirst("<version>" + TARGET_VERSION + "</version>");
            if (!VERSION.matcher(body).find()) {
                normalized = body + "\n      <version>" + TARGET_VERSION + "</version>\n    ";
            }
            String replacement = matcher.group(1) + "mybatis-plus-spring-boot3-starter"
                    + matcher.group(2) + normalized + matcher.group(4);
            matcher.appendReplacement(output, Matcher.quoteReplacement(replacement));
            changed = true;
        }
        matcher.appendTail(output);
        String after = output.toString();
        if (after.contains("<mybatis-plus.version>")) {
            after = after.replaceAll("<mybatis-plus\\.version>[^<]+</mybatis-plus\\.version>",
                    "<mybatis-plus.version>" + TARGET_VERSION + "</mybatis-plus.version>");
        }
        if (changed || !after.equals(before)) {
            Files.writeString(pom, after, StandardCharsets.UTF_8);
            modified.add(relative(root, pom));
            rules.add("MYBATIS_PLUS_BOOT3_STARTER_3_5_17");
        }
    }

    private static void rewritePluginConfiguration(
            Path root,
            Path file,
            Set<String> modified,
            List<String> rules,
            List<String> blockers
    ) throws IOException {
        String before = Files.readString(file, StandardCharsets.UTF_8);
        if (!before.contains("PaginationInterceptor") && !before.contains("TenantSqlParser")) {
            return;
        }
        Matcher dbType = DB_TYPE.matcher(before);
        if (before.contains("PaginationInterceptor") && !dbType.find()) {
            blockers.add(relative(root, file)
                    + ": PaginationInterceptor database type is not explicit; PaginationInnerInterceptor was not guessed");
            return;
        }
        if (before.contains("TenantSqlParser") || before.contains("TenantHandler")) {
            blockers.add(relative(root, file)
                    + ": tenant SQL semantics require an explicit TenantLineHandler contract");
            return;
        }
        String database = dbType.group(1);
        String after = before
                .replace("import com.baomidou.mybatisplus.extension.plugins.PaginationInterceptor;",
                        "import com.baomidou.mybatisplus.extension.plugins.MybatisPlusInterceptor;\n"
                                + "import com.baomidou.mybatisplus.extension.plugins.inner.PaginationInnerInterceptor;")
                .replace("PaginationInterceptor paginationInterceptor()",
                        "MybatisPlusInterceptor mybatisPlusInterceptor()")
                .replace("PaginationInterceptor paginationInterceptor ()",
                        "MybatisPlusInterceptor mybatisPlusInterceptor ()");

        Pattern returnPattern = Pattern.compile("return\\s+new\\s+PaginationInterceptor\\s*\\(\\s*\\)\\s*;");
        Matcher returnMatcher = returnPattern.matcher(after);
        if (!returnMatcher.find()) {
            blockers.add(relative(root, file)
                    + ": PaginationInterceptor construction is customized and cannot be normalized safely");
            return;
        }
        String replacement = "MybatisPlusInterceptor interceptor = new MybatisPlusInterceptor();\n"
                + "        interceptor.addInnerInterceptor(new PaginationInnerInterceptor(DbType." + database + "));\n"
                + "        return interceptor;";
        after = returnMatcher.replaceFirst(Matcher.quoteReplacement(replacement));
        if (!after.equals(before)) {
            Files.writeString(file, after, StandardCharsets.UTF_8);
            modified.add(relative(root, file));
            rules.add("MYBATIS_PLUS_PAGINATION_INNER_INTERCEPTOR");
        }
    }

    private static String relative(Path root, Path file) {
        return root.relativize(file).toString().replace('\\', '/');
    }
}
