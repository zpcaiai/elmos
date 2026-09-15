package io.elmos.worker.web;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Modernizes legacy Spring Web packaging and file-upload mechanisms:
 * <ol>
 *   <li><b>WAR to Executable Fat JAR Migration:</b>
 *       Converts {@code <packaging>war</packaging>} to {@code <packaging>jar</packaging>},
 *       removes {@code <scope>provided</scope>} from embedded Tomcat dependencies,
 *       and ensures {@code SpringBootServletInitializer} classes have a runnable {@code main} method.</li>
 *   <li><b>CommonsMultipartResolver to StandardServletMultipartResolver:</b>
 *       Eliminates deprecated Apache Commons FileUpload / {@code CommonsMultipartResolver},
 *       modernizing to Servlet 6 / Spring 6 {@code StandardServletMultipartResolver}.</li>
 * </ol>
 */
public final class SpringWebLegacyPackagingModernizer {

    public record PackagingModernizationResult(
            boolean modified,
            int changesCount,
            Set<String> modifiedFiles,
            List<String> rulesApplied
    ) {
        public static PackagingModernizationResult empty() {
            return new PackagingModernizationResult(false, 0, Collections.emptySet(), Collections.emptyList());
        }
    }

    private static final Pattern PACKAGING_WAR = Pattern.compile("<packaging>\\s*war\\s*</packaging>");
    private static final Pattern TOMCAT_PROVIDED = Pattern.compile(
            "(<dependency>\\s*<groupId>org\\.springframework\\.boot</groupId>\\s*<artifactId>spring-boot-starter-tomcat</artifactId>\\s*)<scope>provided</scope>(\\s*</dependency>)",
            Pattern.DOTALL
    );
    private static final Pattern COMMONS_FILEUPLOAD_DEP = Pattern.compile(
            "<dependency>\\s*<groupId>commons-fileupload</groupId>\\s*<artifactId>commons-fileupload</artifactId>\\s*<version>[^<]+</version>\\s*</dependency>",
            Pattern.DOTALL
    );

    private SpringWebLegacyPackagingModernizer() {}

    public static PackagingModernizationResult modernize(Path projectRoot) {
        Objects.requireNonNull(projectRoot, "projectRoot cannot be null");
        if (!Files.isDirectory(projectRoot)) {
            return PackagingModernizationResult.empty();
        }

        Set<String> modifiedFiles = new LinkedHashSet<>();
        List<String> rulesApplied = new ArrayList<>();
        int changes = 0;

        try {
            // 1. Modernize pom.xml
            Path pomFile = projectRoot.resolve("pom.xml");
            if (Files.isRegularFile(pomFile)) {
                String pomContent = Files.readString(pomFile, StandardCharsets.UTF_8);
                String updatedPom = pomContent;

                if (PACKAGING_WAR.matcher(updatedPom).find()) {
                    updatedPom = PACKAGING_WAR.matcher(updatedPom).replaceAll("<packaging>jar</packaging>");
                    rulesApplied.add("RULE_WAR_PACKAGING_TO_JAR");
                    changes++;
                }

                Matcher tomcatMatcher = TOMCAT_PROVIDED.matcher(updatedPom);
                if (tomcatMatcher.find()) {
                    updatedPom = tomcatMatcher.replaceAll("$1$2");
                    rulesApplied.add("RULE_TOMCAT_PROVIDED_SCOPE_REMOVED");
                    changes++;
                }

                Matcher commonsUploadMatcher = COMMONS_FILEUPLOAD_DEP.matcher(updatedPom);
                if (commonsUploadMatcher.find()) {
                    updatedPom = commonsUploadMatcher.replaceAll("");
                    rulesApplied.add("RULE_COMMONS_FILEUPLOAD_DEP_REMOVED");
                    changes++;
                }

                if (!updatedPom.equals(pomContent)) {
                    Files.writeString(pomFile, updatedPom, StandardCharsets.UTF_8);
                    modifiedFiles.add(projectRoot.relativize(pomFile).toString());
                }
            }

            // 2. Modernize Java sources
            List<Path> javaFiles;
            try (var stream = Files.walk(projectRoot)) {
                javaFiles = stream.filter(Files::isRegularFile)
                        .filter(p -> p.toString().endsWith(".java"))
                        .toList();
            }

            for (Path javaFile : javaFiles) {
                String content = Files.readString(javaFile, StandardCharsets.UTF_8);
                String updated = content;

                // Modernize CommonsMultipartResolver
                if (updated.contains("CommonsMultipartResolver")) {
                    updated = updated.replace(
                            "org.springframework.web.multipart.commons.CommonsMultipartResolver",
                            "org.springframework.web.multipart.support.StandardServletMultipartResolver"
                    );
                    updated = updated.replace(
                            "new CommonsMultipartResolver()",
                            "new StandardServletMultipartResolver()"
                    );
                    updated = updated.replace(
                            "CommonsMultipartResolver",
                            "StandardServletMultipartResolver"
                    );
                    rulesApplied.add("RULE_COMMONS_MULTIPART_RESOLVER_TO_STANDARD");
                    changes++;
                }

                // Modernize SpringBootServletInitializer to add standalone main method if absent
                if (updated.contains("extends SpringBootServletInitializer") && !updated.contains("public static void main")) {
                    Pattern classDecl = Pattern.compile("public\\s+class\\s+([A-Za-z0-9_]+)\\s+extends\\s+SpringBootServletInitializer\\s*\\{");
                    Matcher classMatcher = classDecl.matcher(updated);
                    if (classMatcher.find()) {
                        String className = classMatcher.group(1);
                        String mainMethod = String.format(
                                """
                                    public static void main(String[] args) {
                                        org.springframework.boot.SpringApplication.run(%s.class, args);
                                    }
                                """,
                                className
                        );
                        int insertIndex = classMatcher.end();
                        updated = updated.substring(0, insertIndex) + "\n" + mainMethod + updated.substring(insertIndex);
                        rulesApplied.add("RULE_INJECT_STANDALONE_MAIN_FOR_SERVLET_INITIALIZER");
                        changes++;
                    }
                }

                if (!updated.equals(content)) {
                    Files.writeString(javaFile, updated, StandardCharsets.UTF_8);
                    modifiedFiles.add(projectRoot.relativize(javaFile).toString());
                }
            }

        } catch (IOException e) {
            return PackagingModernizationResult.empty();
        }

        return new PackagingModernizationResult(
                !modifiedFiles.isEmpty(),
                changes,
                modifiedFiles,
                rulesApplied
        );
    }
}
