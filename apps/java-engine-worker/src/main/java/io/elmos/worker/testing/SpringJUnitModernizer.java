package io.elmos.worker.testing;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;

/**
 * Subagent-G: Automated Testing Suite Modernizer (JUnit 4 to JUnit 5 Jupiter).
 *
 * <p>Modernizes enterprise unit and integration test suites:
 * <ol>
 *   <li><b>Annotation Migration:</b>
 *       Converts {@code @Test}, {@code @Before}, {@code @After}, {@code @Ignore} from
 *       {@code org.junit.*} to {@code org.junit.jupiter.api.*}.</li>
 *   <li><b>Spring Extension Runner:</b>
 *       Replaces legacy {@code @RunWith(SpringRunner.class)} with {@code @ExtendWith(SpringExtension.class)}.</li>
 *   <li><b>Assertions Modernization:</b>
 *       Rewrites {@code org.junit.Assert} static assertions to {@code org.junit.jupiter.api.Assertions}.</li>
 *   <li><b>Test Toolchain Alignment:</b>
 *       Ensures {@code spring-boot-starter-test} (Boot 3/4) runs cleanly without legacy vintage-engine errors.</li>
 * </ol>
 */
public final class SpringJUnitModernizer {

    public record TestModernizationResult(
            boolean modified,
            int changesCount,
            Set<String> modifiedFiles,
            List<String> rulesApplied
    ) {
        public static TestModernizationResult empty() {
            return new TestModernizationResult(false, 0, Collections.emptySet(), Collections.emptyList());
        }
    }

    private SpringJUnitModernizer() {}

    public static TestModernizationResult modernize(Path projectRoot) {
        Objects.requireNonNull(projectRoot, "projectRoot cannot be null");
        if (!Files.isDirectory(projectRoot)) {
            return TestModernizationResult.empty();
        }

        Set<String> modifiedFiles = new LinkedHashSet<>();
        List<String> rulesApplied = new ArrayList<>();
        int changes = 0;

        try {
            Path testRoot = projectRoot.resolve("src/test/java");
            if (!Files.isDirectory(testRoot)) {
                testRoot = projectRoot; // Fallback to scanning whole project for test files
            }

            try (var stream = Files.walk(testRoot)) {
                List<Path> testFiles = stream
                        .filter(Files::isRegularFile)
                        .filter(p -> p.toString().endsWith(".java"))
                        .toList();

                for (Path file : testFiles) {
                    String content = Files.readString(file, StandardCharsets.UTF_8);
                    if (isLegacyJunit4Test(content)) {
                        String modernized = modernizeTestContent(content, rulesApplied);
                        if (!modernized.equals(content)) {
                            Files.writeString(file, modernized, StandardCharsets.UTF_8);
                            String rel = projectRoot.relativize(file).toString().replace("\\", "/");
                            modifiedFiles.add(rel);
                            changes++;
                            ensureJupiterDependencyInPom(file, projectRoot, modifiedFiles, rulesApplied);
                        }
                    }
                }
            }

        } catch (IOException e) {
            return TestModernizationResult.empty();
        }

        return new TestModernizationResult(!modifiedFiles.isEmpty(), changes, modifiedFiles, rulesApplied);
    }

    private static boolean isLegacyJunit4Test(String content) {
        return content.contains("org.junit.Test")
                || content.contains("org.junit.runner.RunWith")
                || content.contains("org.junit.Assert")
                || content.contains("org.junit.Before")
                || content.contains("org.junit.After")
                || content.contains("org.junit.BeforeClass")
                || content.contains("org.junit.AfterClass")
                || content.contains("org.junit.Ignore")
                || content.contains("SpringRunner")
                || content.contains("SpringJUnit4ClassRunner")
                || content.contains("@RunWith");
    }

    private static String modernizeTestContent(String content, List<String> rules) {
        String code = content;

        // 1. Imports modernization
        if (code.contains("import org.junit.Test;")) {
            code = code.replace("import org.junit.Test;", "import org.junit.jupiter.api.Test;");
            rules.add("RULE-JUNIT4-TEST-TO-JUPITER");
        }
        if (code.contains("import org.junit.BeforeClass;")) {
            code = code.replace("import org.junit.BeforeClass;", "import org.junit.jupiter.api.BeforeAll;");
            rules.add("RULE-JUNIT4-BEFORE_CLASS-TO-BEFORE_ALL");
        }
        if (code.contains("import org.junit.AfterClass;")) {
            code = code.replace("import org.junit.AfterClass;", "import org.junit.jupiter.api.AfterAll;");
            rules.add("RULE-JUNIT4-AFTER_CLASS-TO-AFTER_ALL");
        }
        if (code.contains("import org.junit.Before;")) {
            code = code.replace("import org.junit.Before;", "import org.junit.jupiter.api.BeforeEach;");
            rules.add("RULE-JUNIT4-BEFORE-TO-BEFORE_EACH");
        }
        if (code.contains("import org.junit.After;")) {
            code = code.replace("import org.junit.After;", "import org.junit.jupiter.api.AfterEach;");
            rules.add("RULE-JUNIT4-AFTER-TO-AFTER_EACH");
        }
        if (code.contains("import org.junit.Ignore;")) {
            code = code.replace("import org.junit.Ignore;", "import org.junit.jupiter.api.Disabled;");
            rules.add("RULE-JUNIT4-IGNORE-TO-DISABLED");
        }
        if (code.contains("import org.junit.runner.RunWith;")) {
            code = code.replace("import org.junit.runner.RunWith;", "import org.junit.jupiter.api.extension.ExtendWith;");
            rules.add("RULE-JUNIT4-RUNWITH-TO-EXTENDWITH");
        }
        if (code.contains("import org.springframework.test.context.junit4.SpringRunner;")) {
            code = code.replace("import org.springframework.test.context.junit4.SpringRunner;",
                    "import org.springframework.test.context.junit.jupiter.SpringExtension;");
            rules.add("RULE-SPRINGRUNNER-TO-SPRINGEXTENSION");
        }
        if (code.contains("import org.springframework.test.context.junit4.SpringJUnit4ClassRunner;")) {
            code = code.replace("import org.springframework.test.context.junit4.SpringJUnit4ClassRunner;",
                    "import org.springframework.test.context.junit.jupiter.SpringExtension;");
            rules.add("RULE-SPRINGJUNIT4CLASSRUNNER-TO-SPRINGEXTENSION");
        }
        if (code.contains("import org.junit.Assert;")) {
            code = code.replace("import org.junit.Assert;", "import org.junit.jupiter.api.Assertions;");
            rules.add("RULE-JUNIT4-ASSERT-TO-JUPITER");
        }
        if (code.contains("import static org.junit.Assert.")) {
            code = code.replaceAll("import static org.junit.Assert\\.([a-zA-Z0-9_*]+);", "import static org.junit.jupiter.api.Assertions.$1;");
            rules.add("RULE-JUNIT4-ASSERT-STATIC-TO-JUPITER");
        }

        // 2. Annotations rewriting
        if (code.contains("@RunWith")) {
            code = code.replaceAll("@RunWith\\s*\\(\\s*(?:SpringRunner|SpringJUnit4ClassRunner)\\.class\\s*\\)", "@ExtendWith(SpringExtension.class)");
            rules.add("RULE-RUNWITH-SPRING-TO-EXTENDWITH");
            if (code.contains("@ExtendWith") && !code.contains("import org.junit.jupiter.api.extension.ExtendWith;")) {
                code = addImportIfMissing(code, "org.junit.jupiter.api.extension.ExtendWith");
            }
            if (code.contains("SpringExtension.class") && !code.contains("import org.springframework.test.context.junit.jupiter.SpringExtension;")) {
                code = addImportIfMissing(code, "org.springframework.test.context.junit.jupiter.SpringExtension");
            }
        }
        code = code.replaceAll("@BeforeClass\\b(?![a-zA-Z0-9_])", "@BeforeAll");
        code = code.replaceAll("@AfterClass\\b(?![a-zA-Z0-9_])", "@AfterAll");
        code = code.replaceAll("@Before\\b(?![a-zA-Z0-9_])", "@BeforeEach");
        code = code.replaceAll("@After\\b(?![a-zA-Z0-9_])", "@AfterEach");
        code = code.replaceAll("@Ignore\\b(?![a-zA-Z0-9_])", "@Disabled");

        // 3. Assertions method calls
        code = code.replaceAll("\\bAssert\\.", "Assertions.");

        return code;
    }

    private static void ensureJupiterDependencyInPom(Path file, Path projectRoot, Set<String> modifiedFiles, List<String> rules) {
        Path curr = file.getParent();
        Path pom = null;
        while (curr != null && curr.startsWith(projectRoot)) {
            Path candidate = curr.resolve("pom.xml");
            if (Files.isRegularFile(candidate)) {
                pom = candidate;
                break;
            }
            curr = curr.getParent();
        }
        if (pom == null) {
            Path rootPom = projectRoot.resolve("pom.xml");
            if (Files.isRegularFile(rootPom)) {
                pom = rootPom;
            }
        }
        if (pom != null) {
            try {
                String pomContent = Files.readString(pom, StandardCharsets.UTF_8);
                if (!pomContent.contains("junit-jupiter") && !pomContent.contains("spring-boot-starter-test") && pomContent.contains("<dependencies>")) {
                    String jupiterDep = "\n        <dependency>\n"
                            + "            <groupId>org.junit.jupiter</groupId>\n"
                            + "            <artifactId>junit-jupiter</artifactId>\n"
                            + "            <version>5.10.2</version>\n"
                            + "            <scope>test</scope>\n"
                            + "        </dependency>";
                    String updated = pomContent.replace("<dependencies>", "<dependencies>" + jupiterDep);
                    Files.writeString(pom, updated, StandardCharsets.UTF_8);
                    modifiedFiles.add(projectRoot.relativize(pom).toString().replace("\\", "/"));
                    rules.add("RULE-POM-INJECT-JUNIT-JUPITER");
                }
            } catch (IOException ignored) {}
        }
    }

    private static String addImportIfMissing(String code, String fqcn) {
        String importStatement = "import " + fqcn + ";\n";
        if (code.contains("import " + fqcn + ";")) {
            return code;
        }
        int pkgIdx = code.indexOf("package ");
        if (pkgIdx >= 0) {
            int semiIdx = code.indexOf(";", pkgIdx);
            if (semiIdx >= 0) {
                return code.substring(0, semiIdx + 1) + "\n\n" + importStatement + code.substring(semiIdx + 1);
            }
        }
        return importStatement + code;
    }
}
