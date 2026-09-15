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
 * Industrial-grade Spring Boot 3 / Jakarta PageHelper migration operator.
 *
 * <p>Modernizes enterprise pagination infrastructure for legacy MyBatis projects:
 * <ol>
 *   <li>Upgrades {@code pagehelper-spring-boot-starter} from 1.x to 2.1.0+ (Jakarta EE & Spring Boot 3 compatible).</li>
 *   <li>Upgrades standalone {@code pagehelper} from 4.x/5.x to 6.1.0+.</li>
 *   <li>Rewrites deprecated {@code com.github.pagehelper.PageHelper} bean configurations to modern {@code PageInterceptor}.</li>
 * </ol>
 */
public final class SpringPageHelperModernizer {

    public static final String TARGET_STARTER_VERSION = "2.1.0";
    public static final String TARGET_STANDALONE_VERSION = "6.1.0";

    public record ModernizationResult(
            boolean modified,
            Set<String> modifiedFiles,
            List<String> rulesApplied,
            List<String> blockingObligations
    ) {
        public static ModernizationResult empty() {
            return new ModernizationResult(false, Set.of(), List.of(), List.of());
        }
    }

    private static final Pattern STARTER_DEPENDENCY = Pattern.compile(
            "(?s)(<dependency>\\s*<groupId>com\\.github\\.pagehelper</groupId>\\s*<artifactId>)"
                    + "pagehelper-spring-boot-starter(</artifactId>)"
                    + "((?:(?!</dependency>).)*?)(</dependency>)");

    private static final Pattern STANDALONE_DEPENDENCY = Pattern.compile(
            "(?s)(<dependency>\\s*<groupId>com\\.github\\.pagehelper</groupId>\\s*<artifactId>)"
                    + "pagehelper(</artifactId>)"
                    + "((?:(?!</dependency>).)*?)(</dependency>)");

    private static final Pattern VERSION_TAG = Pattern.compile("<version>[^<]+</version>");

    private SpringPageHelperModernizer() {}

    public static ModernizationResult modernize(Path projectRoot) {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        if (!Files.isDirectory(projectRoot)) {
            return ModernizationResult.empty();
        }

        Set<String> modified = new LinkedHashSet<>();
        List<String> rules = new ArrayList<>();
        List<String> blockers = new ArrayList<>();

        try (var stream = Files.walk(projectRoot)) {
            for (Path file : stream.filter(Files::isRegularFile).toList()) {
                String name = file.getFileName().toString();
                if (name.equals("pom.xml")) {
                    rewritePom(projectRoot, file, modified, rules);
                } else if (name.endsWith(".java")) {
                    rewriteJavaConfiguration(projectRoot, file, modified, rules, blockers);
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
        String after = before;
        boolean changed = false;

        // 1. pagehelper-spring-boot-starter upgrade
        Matcher starterMatcher = STARTER_DEPENDENCY.matcher(after);
        StringBuffer starterBuf = new StringBuffer();
        while (starterMatcher.find()) {
            String body = starterMatcher.group(3);
            String normalized;
            if (VERSION_TAG.matcher(body).find()) {
                normalized = VERSION_TAG.matcher(body).replaceFirst("<version>" + TARGET_STARTER_VERSION + "</version>");
            } else {
                normalized = body + "\n      <version>" + TARGET_STARTER_VERSION + "</version>\n    ";
            }
            String replacement = starterMatcher.group(1) + "pagehelper-spring-boot-starter"
                    + starterMatcher.group(2) + normalized + starterMatcher.group(4);
            starterMatcher.appendReplacement(starterBuf, Matcher.quoteReplacement(replacement));
            changed = true;
            rules.add("PAGEHELPER_STARTER_BOOT3_JAKARTA_2_1_0");
        }
        starterMatcher.appendTail(starterBuf);
        after = starterBuf.toString();

        // 2. standalone pagehelper upgrade
        Matcher standaloneMatcher = STANDALONE_DEPENDENCY.matcher(after);
        StringBuffer standaloneBuf = new StringBuffer();
        while (standaloneMatcher.find()) {
            String body = standaloneMatcher.group(3);
            String normalized;
            if (VERSION_TAG.matcher(body).find()) {
                normalized = VERSION_TAG.matcher(body).replaceFirst("<version>" + TARGET_STANDALONE_VERSION + "</version>");
            } else {
                normalized = body + "\n      <version>" + TARGET_STANDALONE_VERSION + "</version>\n    ";
            }
            String replacement = standaloneMatcher.group(1) + "pagehelper"
                    + standaloneMatcher.group(2) + normalized + standaloneMatcher.group(4);
            standaloneMatcher.appendReplacement(standaloneBuf, Matcher.quoteReplacement(replacement));
            changed = true;
            rules.add("PAGEHELPER_STANDALONE_BOOT3_6_1_0");
        }
        standaloneMatcher.appendTail(standaloneBuf);
        after = standaloneBuf.toString();

        // 3. Properties tag upgrade
        if (after.contains("<pagehelper.version>")) {
            after = after.replaceAll("<pagehelper\\.version>[^<]+</pagehelper\\.version>",
                    "<pagehelper.version>" + TARGET_STANDALONE_VERSION + "</pagehelper.version>");
            changed = true;
        }
        if (after.contains("<pagehelper.boot.version>")) {
            after = after.replaceAll("<pagehelper\\.boot\\.version>[^<]+</pagehelper\\.boot\\.version>",
                    "<pagehelper.boot.version>" + TARGET_STARTER_VERSION + "</pagehelper.boot.version>");
            changed = true;
        }
        if (after.contains("<pagehelper-spring-boot-starter.version>")) {
            after = after.replaceAll("<pagehelper-spring-boot-starter\\.version>[^<]+</pagehelper-spring-boot-starter\\.version>",
                    "<pagehelper-spring-boot-starter.version>" + TARGET_STARTER_VERSION + "</pagehelper-spring-boot-starter.version>");
            changed = true;
        }

        if (changed && !after.equals(before)) {
            Files.writeString(pom, after, StandardCharsets.UTF_8);
            modified.add(relative(root, pom));
        }
    }

    private static void rewriteJavaConfiguration(
            Path root,
            Path file,
            Set<String> modified,
            List<String> rules,
            List<String> blockers
    ) throws IOException {
        String before = Files.readString(file, StandardCharsets.UTF_8);
        if (!before.contains("com.github.pagehelper") && !before.contains("PageHelper") && !before.contains("PageInterceptor")) {
            return;
        }

        String after = before;
        boolean changed = false;

        // Legacy PageHelper class bean -> PageInterceptor bean
        if (after.contains("import com.github.pagehelper.PageHelper;") || after.contains("new PageHelper()")) {
            after = after.replace("import com.github.pagehelper.PageHelper;", "import com.github.pagehelper.PageInterceptor;");
            after = after.replaceAll("public\\s+PageHelper\\s+pageHelper\\s*\\(\\s*\\)", "public PageInterceptor pageInterceptor()");
            after = after.replaceAll("PageHelper\\s+pageHelper\\s*=\\s*new\\s+PageHelper\\s*\\(\\s*\\);", "PageInterceptor pageInterceptor = new PageInterceptor();");
            after = after.replaceAll("return\\s+pageHelper;", "return pageInterceptor;");
            after = after.replaceAll("new\\s+PageHelper\\s*\\(\\s*\\)", "new PageInterceptor()");
            changed = true;
            rules.add("PAGEHELPER_BEAN_TO_PAGE_INTERCEPTOR");
        }

        if (changed && !after.equals(before)) {
            Files.writeString(file, after, StandardCharsets.UTF_8);
            modified.add(relative(root, file));
        }
    }

    private static String relative(Path root, Path file) {
        return root.relativize(file).toString().replace('\\', '/');
    }
}
