package io.elmos.worker.testing;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Industrial-grade PowerMock Elimination & Mockito 5 Modernizer.
 *
 * <p>Removes deprecated, byte-code manipulating PowerMock infrastructure incompatible with Java 17/21
 * strong encapsulation, converting suites to native Mockito 5.x (@ExtendWith(MockitoExtension.class)
 * and MockedStatic try-with-resources).
 *
 * <ol>
 *   <li>Removes {@code @RunWith(PowerMockRunner.class)} and replaces with {@code @ExtendWith(MockitoExtension.class)}.</li>
 *   <li>Eliminates {@code @PrepareForTest({ ... })} annotations completely.</li>
 *   <li>Rewrites {@code PowerMockito.mockStatic(X.class)} + {@code PowerMockito.when(...)} into Mockito 5 {@code MockedStatic<X>}.</li>
 *   <li>Replaces {@code PowerMockito.mock/spy/when} with standard {@code Mockito} equivalents.</li>
 *   <li>Cleans up {@code org.powermock} Maven dependencies from {@code pom.xml} and ensures {@code mockito-core:5.11.0}.</li>
 * </ol>
 */
public final class SpringPowerMockEliminator {

    public static final String MOCKITO_VERSION = "5.11.0";

    public record EliminationResult(
            boolean modified,
            int changesCount,
            Set<String> modifiedFiles,
            List<String> rulesApplied,
            List<String> warnings
    ) {
        public static EliminationResult empty() {
            return new EliminationResult(false, 0, Collections.emptySet(), Collections.emptyList(), Collections.emptyList());
        }
    }

    private static final Pattern POWERMOCK_DEPENDENCY = Pattern.compile(
            "(?s)<dependency>\\s*<groupId>org\\.powermock</groupId>\\s*<artifactId>[^<]+</artifactId>.*?Cached?\\s*</dependency>|<dependency>\\s*<groupId>org\\.powermock</groupId>\\s*<artifactId>[^<]+</artifactId>.*?</dependency>");

    private static final Pattern PREPARE_FOR_TEST = Pattern.compile("@PrepareForTest\\s*\\(\\s*\\{[^}]*\\}\\s*\\)|@PrepareForTest\\s*\\([^)]*\\)");

    private static final Pattern POWERMOCK_RUNNER = Pattern.compile("@RunWith\\s*\\(\\s*PowerMockRunner\\.class\\s*\\)");

    private static final Pattern MOCK_STATIC_CALL = Pattern.compile("PowerMockito\\.mockStatic\\s*\\(\\s*([A-Za-z0-9_]+)\\.class\\s*\\)\\s*;");

    private SpringPowerMockEliminator() {}

    public static EliminationResult eliminate(Path projectRoot) {
        Objects.requireNonNull(projectRoot, "projectRoot cannot be null");
        if (!Files.isDirectory(projectRoot)) {
            return EliminationResult.empty();
        }

        Set<String> modifiedFiles = new LinkedHashSet<>();
        List<String> rulesApplied = new ArrayList<>();
        List<String> warnings = new ArrayList<>();
        int changes = 0;

        try {
            // 1. Process pom.xml
            Path pomFile = projectRoot.resolve("pom.xml");
            if (Files.isRegularFile(pomFile)) {
                String beforePom = Files.readString(pomFile, StandardCharsets.UTF_8);
                String afterPom = modernizePom(beforePom, rulesApplied);
                if (!afterPom.equals(beforePom)) {
                    Files.writeString(pomFile, afterPom, StandardCharsets.UTF_8);
                    modifiedFiles.add(relative(projectRoot, pomFile));
                    changes++;
                }
            }

            // 2. Process Java Test Files
            Path testRoot = projectRoot.resolve("src/test/java");
            if (!Files.isDirectory(testRoot)) {
                testRoot = projectRoot;
            }

            try (var stream = Files.walk(testRoot)) {
                List<Path> testFiles = stream
                        .filter(Files::isRegularFile)
                        .filter(p -> p.toString().endsWith(".java"))
                        .toList();

                for (Path testFile : testFiles) {
                    String content = Files.readString(testFile, StandardCharsets.UTF_8);
                    if (isPowerMockTest(content)) {
                        String modernized = modernizeJavaTest(content, rulesApplied, warnings);
                        if (!modernized.equals(content)) {
                            Files.writeString(testFile, modernized, StandardCharsets.UTF_8);
                            modifiedFiles.add(relative(projectRoot, testFile));
                            changes++;
                        }
                    }
                }
            }

        } catch (IOException e) {
            warnings.add("IO error during PowerMock elimination: " + e.getMessage());
        }

        return new EliminationResult(!modifiedFiles.isEmpty(), changes, Collections.unmodifiableSet(modifiedFiles),
                List.copyOf(rulesApplied), List.copyOf(warnings));
    }

    public static boolean isPowerMockTest(String content) {
        return content.contains("org.powermock")
                || content.contains("PowerMockito")
                || content.contains("PowerMockRunner")
                || content.contains("@PrepareForTest");
    }

    public static String modernizePom(String pomContent, List<String> rules) {
        String result = pomContent;
        Matcher m = POWERMOCK_DEPENDENCY.matcher(result);
        if (m.find()) {
            result = m.replaceAll("");
            rules.add("POWERMOCK_POM_DEPENDENCIES_REMOVED");

            // Ensure Mockito 5 dependency is present
            if (!result.contains("mockito-junit-jupiter")) {
                String mockitoDependencies = """
                        <dependency>
                          <groupId>org.mockito</groupId>
                          <artifactId>mockito-core</artifactId>
                          <version>""" + MOCKITO_VERSION + """
                </version>
                          <scope>test</scope>
                        </dependency>
                        <dependency>
                          <groupId>org.mockito</groupId>
                          <artifactId>mockito-junit-jupiter</artifactId>
                          <version>""" + MOCKITO_VERSION + """
                </version>
                          <scope>test</scope>
                        </dependency>
                    """;
                if (result.contains("</dependencies>")) {
                    result = result.replace("</dependencies>", mockitoDependencies + "  </dependencies>");
                    rules.add("MOCKITO_5_JUPITER_DEPENDENCIES_ADDED");
                }
            }
        }
        return result;
    }

    public static String modernizeJavaTest(String source, List<String> rules, List<String> warnings) {
        String result = source;

        // 1. Runner replacement: @RunWith(PowerMockRunner.class) -> @ExtendWith(MockitoExtension.class)
        if (POWERMOCK_RUNNER.matcher(result).find()) {
            result = POWERMOCK_RUNNER.matcher(result).replaceAll("@ExtendWith(MockitoExtension.class)");
            rules.add("POWERMOCK_RUNNER_TO_MOCKITO_EXTENSION");
        }

        // 2. Remove @PrepareForTest
        if (PREPARE_FOR_TEST.matcher(result).find()) {
            result = PREPARE_FOR_TEST.matcher(result).replaceAll("");
            rules.add("POWERMOCK_PREPARE_FOR_TEST_REMOVED");
        }

        // 3. Transform PowerMockito.mockStatic(...)
        Matcher staticMatcher = MOCK_STATIC_CALL.matcher(result);
        if (staticMatcher.find()) {
            StringBuffer sb = new StringBuffer();
            staticMatcher.reset();
            while (staticMatcher.find()) {
                String targetClass = staticMatcher.group(1);
                String varName = "mocked" + targetClass;
                String replacement = "try (MockedStatic<" + targetClass + "> " + varName + " = mockStatic(" + targetClass + ".class)) {";
                staticMatcher.appendReplacement(sb, Matcher.quoteReplacement(replacement));
                rules.add("POWERMOCK_MOCK_STATIC_TO_MOCKED_STATIC");
            }
            staticMatcher.appendTail(sb);
            result = sb.toString();

            // Transform subsequent PowerMockito.when(Target.method(...)) to mockedTarget.when(() -> Target.method(...))
            Pattern whenPattern = Pattern.compile("PowerMockito\\.when\\s*\\(\\s*([A-Za-z0-9_]+)\\.([A-Za-z0-9_]+)\\s*\\(([^)]*)\\)\\s*\\)");
            Matcher whenMatcher = whenPattern.matcher(result);
            if (whenMatcher.find()) {
                StringBuffer whenSb = new StringBuffer();
                whenMatcher.reset();
                while (whenMatcher.find()) {
                    String targetClass = whenMatcher.group(1);
                    String method = whenMatcher.group(2);
                    String args = whenMatcher.group(3);
                    String varName = "mocked" + targetClass;
                    String replacement = varName + ".when(() -> " + targetClass + "." + method + "(" + args + "))";
                    whenMatcher.appendReplacement(whenSb, Matcher.quoteReplacement(replacement));
                }
                whenMatcher.appendTail(whenSb);
                result = whenSb.toString();
            }

            // Close the try block at the end of test methods that contain mockStatic
            result = closeTryBlocksForMockStatic(result);
        }

        // 4. Transform standard PowerMockito calls to Mockito
        if (result.contains("PowerMockito.mock(")) {
            result = result.replace("PowerMockito.mock(", "Mockito.mock(");
            rules.add("POWERMOCK_MOCK_TO_MOCKITO_MOCK");
        }
        if (result.contains("PowerMockito.spy(")) {
            result = result.replace("PowerMockito.spy(", "Mockito.spy(");
            rules.add("POWERMOCK_SPY_TO_MOCKITO_SPY");
        }
        if (result.contains("PowerMockito.when(")) {
            result = result.replace("PowerMockito.when(", "Mockito.when(");
            rules.add("POWERMOCK_WHEN_TO_MOCKITO_WHEN");
        }
        if (result.contains("PowerMockito.doReturn(")) {
            result = result.replace("PowerMockito.doReturn(", "Mockito.doReturn(");
            rules.add("POWERMOCK_DO_RETURN_TO_MOCKITO");
        }
        if (result.contains("PowerMockito.doNothing(")) {
            result = result.replace("PowerMockito.doNothing(", "Mockito.doNothing(");
            rules.add("POWERMOCK_DO_NOTHING_TO_MOCKITO");
        }
        if (result.contains("PowerMockito.doThrow(")) {
            result = result.replace("PowerMockito.doThrow(", "Mockito.doThrow(");
            rules.add("POWERMOCK_DO_THROW_TO_MOCKITO");
        }
        if (result.contains("PowerMockito.verify(")) {
            result = result.replace("PowerMockito.verify(", "Mockito.verify(");
            rules.add("POWERMOCK_VERIFY_TO_MOCKITO");
        }

        // 5. Clean up imports and add Mockito 5 imports
        result = cleanAndAddImports(result);

        return result;
    }

    private static String closeTryBlocksForMockStatic(String source) {
        String[] lines = source.split("\n", -1);
        List<String> output = new ArrayList<>();
        boolean insideTry = false;
        int braceDepth = 0;
        int targetClosingDepth = 0;

        for (String line : lines) {
            output.add(line);
            if (line.contains("try (MockedStatic<")) {
                insideTry = true;
                targetClosingDepth = braceDepth;
            }
            int openBraces = countMatches(line, '{');
            int closeBraces = countMatches(line, '}');
            braceDepth += (openBraces - closeBraces);

            // If we are reaching the end of the method that opened the try block
            if (insideTry && braceDepth == targetClosingDepth) {
                // Insert closing brace for try block before the method closing brace
                int lastIdx = output.size() - 1;
                output.add(lastIdx, "        }");
                insideTry = false;
            }
        }
        return String.join("\n", output);
    }

    private static int countMatches(String text, char ch) {
        int count = 0;
        for (int i = 0; i < text.length(); i++) {
            if (text.charAt(i) == ch) count++;
        }
        return count;
    }

    private static String cleanAndAddImports(String source) {
        String result = source;
        // Remove PowerMock imports
        result = result.replaceAll("import\\s+org\\.powermock[^;]+;\\s*\\n", "");

        // Add Mockito 5 imports if missing
        StringBuilder importsToAdd = new StringBuilder();
        if (result.contains("@ExtendWith(MockitoExtension.class)") && !result.contains("import org.mockito.junit.jupiter.MockitoExtension;")) {
            importsToAdd.append("import org.mockito.junit.jupiter.MockitoExtension;\n");
        }
        if (result.contains("@ExtendWith(") && !result.contains("import org.junit.jupiter.api.extension.ExtendWith;")) {
            importsToAdd.append("import org.junit.jupiter.api.extension.ExtendWith;\n");
        }
        if (result.contains("MockedStatic") && !result.contains("import org.mockito.MockedStatic;")) {
            importsToAdd.append("import org.mockito.MockedStatic;\n");
        }
        if (result.contains("mockStatic(") && !result.contains("import static org.mockito.Mockito.mockStatic;")) {
            importsToAdd.append("import static org.mockito.Mockito.mockStatic;\n");
        }
        if (result.contains("Mockito.mock(") && !result.contains("import org.mockito.Mockito;")) {
            importsToAdd.append("import org.mockito.Mockito;\n");
        }

        if (importsToAdd.length() > 0) {
            Pattern pkgPattern = Pattern.compile("package\\s+[^;]+;");
            Matcher pkgMatcher = pkgPattern.matcher(result);
            if (pkgMatcher.find()) {
                result = pkgMatcher.replaceFirst(pkgMatcher.group() + "\n\n" + importsToAdd.toString().trim());
            } else {
                result = importsToAdd.toString() + "\n" + result;
            }
        }

        return result;
    }

    private static String relative(Path root, Path file) {
        return root.relativize(file).toString().replace('\\', '/');
    }
}
