package io.elmos.worker.cloud;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Exact Boot 3.5 modernization rules for Spring Cloud Alibaba 2025.0 and Dubbo 3.3. */
public final class SpringAlibabaDubboModernizer {
    static final String ALIBABA_VERSION = "2025.0.0.0";
    static final String DUBBO_VERSION = "3.3.0";

    public record ModernizationResult(
            boolean modified,
            Set<String> modifiedFiles,
            List<String> rulesApplied,
            List<String> blockingObligations
    ) {}

    private static final Pattern VERSIONED_ALIBABA_BOM = Pattern.compile(
            "(?s)(<artifactId>spring-cloud-alibaba-dependencies</artifactId>"
                    + "(?:(?!</dependency>).)*?<version>)[^<]+(</version>)");
    private static final Pattern VERSIONED_DUBBO = Pattern.compile(
            "(?s)(<groupId>(?:com\\.alibaba|org\\.apache\\.dubbo)</groupId>\\s*"
                    + "<artifactId>dubbo-spring-boot-starter(?:3)?</artifactId>"
                    + "(?:(?!</dependency>).)*?<version>)[^<]+(</version>)");
    private static final Pattern LEGACY_DUBBO_COORDINATE = Pattern.compile(
            "(<groupId>)com\\.alibaba(</groupId>\\s*<artifactId>)"
                    + "dubbo-spring-boot-starter(</artifactId>)");

    private SpringAlibabaDubboModernizer() {}

    public static ModernizationResult modernize(Path projectRoot) {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        Set<String> filesChanged = new LinkedHashSet<>();
        List<String> rules = new ArrayList<>();
        List<String> blockers = new ArrayList<>();
        if (!Files.isDirectory(projectRoot)) {
            return new ModernizationResult(false, filesChanged, rules, List.of("project root does not exist"));
        }
        try (var files = Files.walk(projectRoot)) {
            for (Path file : files.filter(Files::isRegularFile).toList()) {
                String name = file.getFileName().toString();
                if (name.equals("pom.xml")) rewritePom(projectRoot, file, filesChanged, rules);
                else if (name.endsWith(".java")) rewriteJava(projectRoot, file, filesChanged, rules);
                else if (name.startsWith("bootstrap.") || name.startsWith("application.")) {
                    rewriteNacosConfig(projectRoot, file, filesChanged, rules);
                } else if (name.endsWith(".xml")) inspectDubboXml(projectRoot, file, blockers);
            }
        } catch (IOException e) {
            blockers.add("IO:" + e.getClass().getSimpleName());
        }
        return new ModernizationResult(!filesChanged.isEmpty(), Set.copyOf(filesChanged),
                List.copyOf(rules), List.copyOf(blockers));
    }

    private static void rewritePom(Path root, Path pom, Set<String> changed, List<String> rules)
            throws IOException {
        String before = Files.readString(pom, StandardCharsets.UTF_8);
        String after = VERSIONED_ALIBABA_BOM.matcher(before)
                .replaceAll("$1" + ALIBABA_VERSION + "$2");
        if (after.contains("com.alibaba.cloud") && after.contains("spring-cloud-starter-alibaba-seata")) {
            after = after.replace("<artifactId>spring-cloud-starter-alibaba-seata</artifactId>",
                    "<artifactId>spring-cloud-starter-alibaba-seata</artifactId>");
        }
        after = LEGACY_DUBBO_COORDINATE.matcher(after)
                .replaceAll("$1org.apache.dubbo$2dubbo-spring-boot-starter3$3");
        Matcher dubbo = VERSIONED_DUBBO.matcher(after);
        after = dubbo.replaceAll("$1" + DUBBO_VERSION + "$2");
        if (!after.equals(before)) {
            Files.writeString(pom, after, StandardCharsets.UTF_8);
            changed.add(relative(root, pom));
            if (before.contains("spring-cloud-alibaba-dependencies")) rules.add("SCA_2025_0_BOOT_3_5_BOM");
            if (before.contains("dubbo-spring-boot-starter")) rules.add("DUBBO_3_3_BOOT3_STARTER");
        }
    }

    private static void rewriteJava(Path root, Path file, Set<String> changed, List<String> rules)
            throws IOException {
        String before = Files.readString(file, StandardCharsets.UTF_8);
        String after = before
                .replace("import com.alibaba.dubbo.config.annotation.Service;",
                        "import org.apache.dubbo.config.annotation.DubboService;")
                .replace("import com.alibaba.dubbo.config.annotation.Reference;",
                        "import org.apache.dubbo.config.annotation.DubboReference;")
                .replace("import org.apache.dubbo.config.annotation.Service;",
                        "import org.apache.dubbo.config.annotation.DubboService;")
                .replace("import org.apache.dubbo.config.annotation.Reference;",
                        "import org.apache.dubbo.config.annotation.DubboReference;");
        if (!after.equals(before)) {
            if (after.contains("import org.apache.dubbo.config.annotation.DubboService;")) {
                after = replaceAnnotation(after, "Service", "DubboService");
            }
            if (after.contains("import org.apache.dubbo.config.annotation.DubboReference;")) {
                after = replaceAnnotation(after, "Reference", "DubboReference");
            }
            Files.writeString(file, after, StandardCharsets.UTF_8);
            changed.add(relative(root, file));
            rules.add("DUBBO_LEGACY_ANNOTATIONS_TO_DUBBO_ANNOTATIONS");
        }
    }

    private static String replaceAnnotation(String source, String oldName, String newName) {
        StringBuilder result = new StringBuilder(source.length());
        boolean string = false;
        boolean character = false;
        boolean lineComment = false;
        boolean blockComment = false;
        for (int index = 0; index < source.length();) {
            char current = source.charAt(index);
            char next = index + 1 < source.length() ? source.charAt(index + 1) : '\0';
            if (lineComment) {
                result.append(current); index++;
                if (current == '\n') lineComment = false;
            } else if (blockComment) {
                result.append(current); index++;
                if (current == '*' && next == '/') { result.append(next); index++; blockComment = false; }
            } else if (string || character) {
                result.append(current); index++;
                if (current == '\\' && index < source.length()) result.append(source.charAt(index++));
                else if (string && current == '"') string = false;
                else if (character && current == '\'') character = false;
            } else if (current == '/' && next == '/') {
                result.append("//"); index += 2; lineComment = true;
            } else if (current == '/' && next == '*') {
                result.append("/*"); index += 2; blockComment = true;
            } else if (current == '"') { result.append(current); index++; string = true;
            } else if (current == '\'') { result.append(current); index++; character = true;
            } else if (source.startsWith("@" + oldName, index)
                    && (index + oldName.length() + 1 == source.length()
                    || !Character.isJavaIdentifierPart(source.charAt(index + oldName.length() + 1)))) {
                result.append('@').append(newName); index += oldName.length() + 1;
            } else { result.append(current); index++; }
        }
        return result.toString();
    }

    private static void rewriteNacosConfig(Path root, Path file, Set<String> changed, List<String> rules)
            throws IOException {
        String before = Files.readString(file, StandardCharsets.UTF_8);
        if (!before.contains("nacos") || before.contains("spring.config.import")
                || before.contains("config:\n    import:")) return;
        String entry = file.getFileName().toString().endsWith(".properties")
                ? "\nspring.config.import=optional:nacos:${spring.application.name}.${spring.cloud.nacos.config.file-extension:yaml}\n"
                : "\nspring.config.import: optional:nacos:${spring.application.name}.${spring.cloud.nacos.config.file-extension:yaml}\n";
        Files.writeString(file, before + entry, StandardCharsets.UTF_8);
        changed.add(relative(root, file));
        rules.add("NACOS_CONFIG_DATA_IMPORT");
    }

    private static void inspectDubboXml(Path root, Path file, List<String> blockers) throws IOException {
        String content = Files.readString(file, StandardCharsets.UTF_8);
        if (content.contains("<dubbo:service") || content.contains("<dubbo:reference")) {
            blockers.add(relative(root, file)
                    + ": Dubbo XML service/reference wiring requires bean-identity and lifecycle reconciliation; no annotation was guessed");
        }
    }

    private static String relative(Path root, Path file) {
        return root.relativize(file).toString().replace('\\', '/');
    }
}
