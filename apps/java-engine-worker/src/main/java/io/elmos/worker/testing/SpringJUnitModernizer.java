package io.elmos.worker.testing;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Industrial-grade Automated Testing Suite Modernizer (JUnit 4 to JUnit 5 Jupiter).
 *
 * <p>Modernizes enterprise unit and integration test suites with AST/lexical-level precision:
 * <ol>
 *   <li><b>Annotation Migration:</b>
 *       Converts {@code @Test}, {@code @Before}, {@code @After}, {@code @BeforeClass}, {@code @AfterClass},
 *       {@code @Ignore} from {@code org.junit.*} to {@code org.junit.jupiter.api.*}.</li>
 *   <li><b>Exception & Timeout Modernization:</b>
 *       Rewrites legacy {@code @Test(expected = Foo.class)} into {@code Assertions.assertThrows(Foo.class, () -> { ... })},
 *       and {@code @Test(timeout = N)} into {@code @Timeout(N)}.</li>
 *   <li><b>Runner Migration:</b>
 *       Replaces {@code @RunWith(SpringRunner.class)} and {@code @RunWith(SpringJUnit4ClassRunner.class)}
 *       with {@code @ExtendWith(SpringExtension.class)}, and {@code @RunWith(MockitoJUnitRunner.class)}
 *       with {@code @ExtendWith(MockitoExtension.class)}.</li>
 *   <li><b>Assertion Parameter Reordering (Crucial Semantic Parity):</b>
 *       Reverses inverted parameters between JUnit 4 and JUnit 5:
 *       <ul>
 *         <li>2-arg: {@code assertTrue(msg, cond)} -> {@code assertTrue(cond, msg)}</li>
 *         <li>3-arg: {@code assertEquals(msg, exp, act)} -> {@code assertEquals(exp, act, msg)}</li>
 *         <li>4-arg: {@code assertEquals(msg, exp, act, delta)} -> {@code assertEquals(exp, act, delta, msg)}</li>
 *       </ul>
 *       Uses lexical token depth analysis to guarantee that nested method calls, lambdas, and strings
 *       with commas are never corrupted.</li>
 *   <li><b>POM Alignment:</b>
 *       Ensures {@code junit-jupiter} dependency exists when necessary without introducing duplicate XML tags.</li>
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

    public static boolean isLegacyJunit4Test(String content) {
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
                || content.contains("MockitoJUnitRunner")
                || content.contains("@RunWith")
                || (content.contains("@Test") && (content.contains("expected") || content.contains("timeout")));
    }

    public static String modernizeTestContent(String content) {
        return modernizeTestContent(content, new ArrayList<>());
    }

    public static String modernizeTestContent(String content, List<String> rules) {
        if (content == null || content.isEmpty()) {
            return content;
        }

        String code = content;

        // 1. Modernize Imports with whitespace-tolerant regex
        code = modernizeImports(code, rules);

        // 2. Modernize Runners (@RunWith -> @ExtendWith)
        code = modernizeRunners(code, rules);

        // 3. Modernize Lifecycle Annotations
        code = modernizeLifecycleAnnotations(code, rules);

        // 4. Modernize @Test(expected = ...) to assertThrows(...)
        code = modernizeExpectedException(code, rules);

        // 5. Modernize @Test(timeout = ...) to @Timeout(...)
        code = modernizeTimeoutAnnotation(code, rules);

        // 6. Modernize Assert references and method calls (with parameter reordering)
        code = modernizeAssertions(code, rules);

        return code;
    }

    private static String modernizeImports(String code, List<String> rules) {
        String result = code;

        // org.junit.Test
        if (Pattern.compile("(?m)^\\s*import\\s+org\\.junit\\.Test\\s*;").matcher(result).find()) {
            result = result.replaceAll("(?m)^\\s*import\\s+org\\.junit\\.Test\\s*;", "import org.junit.jupiter.api.Test;");
            rules.add("RULE-JUNIT4-TEST-TO-JUPITER");
        }
        // org.junit.BeforeClass -> org.junit.jupiter.api.BeforeAll
        if (Pattern.compile("(?m)^\\s*import\\s+org\\.junit\\.BeforeClass\\s*;").matcher(result).find()) {
            result = result.replaceAll("(?m)^\\s*import\\s+org\\.junit\\.BeforeClass\\s*;", "import org.junit.jupiter.api.BeforeAll;");
            rules.add("RULE-JUNIT4-BEFORE_CLASS-TO-BEFORE_ALL");
        }
        // org.junit.AfterClass -> org.junit.jupiter.api.AfterAll
        if (Pattern.compile("(?m)^\\s*import\\s+org\\.junit\\.AfterClass\\s*;").matcher(result).find()) {
            result = result.replaceAll("(?m)^\\s*import\\s+org\\.junit\\.AfterClass\\s*;", "import org.junit.jupiter.api.AfterAll;");
            rules.add("RULE-JUNIT4-AFTER_CLASS-TO-AFTER_ALL");
        }
        // org.junit.Before -> org.junit.jupiter.api.BeforeEach
        if (Pattern.compile("(?m)^\\s*import\\s+org\\.junit\\.Before\\s*;").matcher(result).find()) {
            result = result.replaceAll("(?m)^\\s*import\\s+org\\.junit\\.Before\\s*;", "import org.junit.jupiter.api.BeforeEach;");
            rules.add("RULE-JUNIT4-BEFORE-TO-BEFORE_EACH");
        }
        // org.junit.After -> org.junit.jupiter.api.AfterEach
        if (Pattern.compile("(?m)^\\s*import\\s+org\\.junit\\.After\\s*;").matcher(result).find()) {
            result = result.replaceAll("(?m)^\\s*import\\s+org\\.junit\\.After\\s*;", "import org.junit.jupiter.api.AfterEach;");
            rules.add("RULE-JUNIT4-AFTER-TO-AFTER_EACH");
        }
        // org.junit.Ignore -> org.junit.jupiter.api.Disabled
        if (Pattern.compile("(?m)^\\s*import\\s+org\\.junit\\.Ignore\\s*;").matcher(result).find()) {
            result = result.replaceAll("(?m)^\\s*import\\s+org\\.junit\\.Ignore\\s*;", "import org.junit.jupiter.api.Disabled;");
            rules.add("RULE-JUNIT4-IGNORE-TO-DISABLED");
        }
        // org.junit.runner.RunWith -> org.junit.jupiter.api.extension.ExtendWith
        if (Pattern.compile("(?m)^\\s*import\\s+org\\.junit\\.runner\\.RunWith\\s*;").matcher(result).find()) {
            result = result.replaceAll("(?m)^\\s*import\\s+org\\.junit\\.runner\\.RunWith\\s*;", "import org.junit.jupiter.api.extension.ExtendWith;");
            rules.add("RULE-JUNIT4-RUNWITH-TO-EXTENDWITH");
        }
        // SpringRunner / SpringJUnit4ClassRunner -> SpringExtension
        if (Pattern.compile("(?m)^\\s*import\\s+org\\.springframework\\.test\\.context\\.junit4\\.Spring(Runner|JUnit4ClassRunner)\\s*;").matcher(result).find()) {
            result = result.replaceAll("(?m)^\\s*import\\s+org\\.springframework\\.test\\.context\\.junit4\\.Spring(Runner|JUnit4ClassRunner)\\s*;",
                    "import org.springframework.test.context.junit.jupiter.SpringExtension;");
            rules.add("RULE-SPRINGRUNNER-TO-SPRINGEXTENSION");
        }
        // MockitoJUnitRunner -> MockitoExtension
        if (Pattern.compile("(?m)^\\s*import\\s+org\\.mockito\\.(runners|junit)\\.MockitoJUnitRunner\\s*;").matcher(result).find()) {
            result = result.replaceAll("(?m)^\\s*import\\s+org\\.mockito\\.(runners|junit)\\.MockitoJUnitRunner\\s*;",
                    "import org.mockito.junit.jupiter.MockitoExtension;");
            rules.add("RULE-MOCKITO-RUNNER-TO-EXTENSION");
        }
        // org.junit.Assert -> org.junit.jupiter.api.Assertions
        if (Pattern.compile("(?m)^\\s*import\\s+org\\.junit\\.Assert\\s*;").matcher(result).find()) {
            result = result.replaceAll("(?m)^\\s*import\\s+org\\.junit\\.Assert\\s*;", "import org.junit.jupiter.api.Assertions;");
            rules.add("RULE-JUNIT4-ASSERT-TO-JUPITER");
        }
        // Static imports: import static org.junit.Assert.* / method
        if (Pattern.compile("(?m)^\\s*import\\s+static\\s+org\\.junit\\.Assert\\.").matcher(result).find()) {
            result = result.replaceAll("(?m)^\\s*import\\s+static\\s+org\\.junit\\.Assert\\.([a-zA-Z0-9_*]+)\\s*;",
                    "import static org.junit.jupiter.api.Assertions.$1;");
            rules.add("RULE-JUNIT4-ASSERT-STATIC-TO-JUPITER");
        }
        // Wildcard import org.junit.* -> org.junit.jupiter.api.*
        if (Pattern.compile("(?m)^\\s*import\\s+org\\.junit\\.\\*\\s*;").matcher(result).find()) {
            result = result.replaceAll("(?m)^\\s*import\\s+org\\.junit\\.\\*\\s*;", "import org.junit.jupiter.api.*;");
            rules.add("RULE-JUNIT4-WILDCARD-TO-JUPITER");
        }

        return result;
    }

    private static String modernizeRunners(String code, List<String> rules) {
        String result = code;

        // @RunWith(SpringRunner.class) or @RunWith(SpringJUnit4ClassRunner.class)
        Pattern springRunnerPattern = Pattern.compile("@RunWith\\s*\\(\\s*(?:SpringRunner|SpringJUnit4ClassRunner)\\.class\\s*\\)");
        if (springRunnerPattern.matcher(result).find()) {
            result = springRunnerPattern.matcher(result).replaceAll("@ExtendWith(SpringExtension.class)");
            rules.add("RULE-RUNWITH-SPRING-TO-EXTENDWITH");
            result = addImportIfMissing(result, "org.junit.jupiter.api.extension.ExtendWith");
            result = addImportIfMissing(result, "org.springframework.test.context.junit.jupiter.SpringExtension");
        }

        // @RunWith(MockitoJUnitRunner.class)
        Pattern mockitoRunnerPattern = Pattern.compile("@RunWith\\s*\\(\\s*MockitoJUnitRunner(?:\\.Silent)?\\.class\\s*\\)");
        if (mockitoRunnerPattern.matcher(result).find()) {
            result = mockitoRunnerPattern.matcher(result).replaceAll("@ExtendWith(MockitoExtension.class)");
            rules.add("RULE-RUNWITH-MOCKITO-TO-EXTENDWITH");
            result = addImportIfMissing(result, "org.junit.jupiter.api.extension.ExtendWith");
            result = addImportIfMissing(result, "org.mockito.junit.jupiter.MockitoExtension");
        }

        return result;
    }

    private static String modernizeLifecycleAnnotations(String code, List<String> rules) {
        String result = code;
        result = result.replaceAll("@BeforeClass\\b(?![a-zA-Z0-9_])", "@BeforeAll");
        result = result.replaceAll("@AfterClass\\b(?![a-zA-Z0-9_])", "@AfterAll");
        result = result.replaceAll("@Before\\b(?![a-zA-Z0-9_])", "@BeforeEach");
        result = result.replaceAll("@After\\b(?![a-zA-Z0-9_])", "@AfterEach");
        result = result.replaceAll("@Ignore\\b(?![a-zA-Z0-9_])", "@Disabled");
        return result;
    }

    private static String modernizeExpectedException(String code, List<String> rules) {
        Pattern expectedPattern = Pattern.compile("@Test\\s*\\(\\s*expected\\s*=\\s*([a-zA-Z0-9_.]+\\.class)\\s*\\)");
        Matcher matcher = expectedPattern.matcher(code);
        if (!matcher.find()) {
            return code;
        }

        StringBuilder sb = new StringBuilder();
        int lastIndex = 0;

        matcher.reset();
        while (matcher.find()) {
            String exceptionClass = matcher.group(1);
            int testAnnoStart = matcher.start();
            sb.append(code, lastIndex, testAnnoStart);

            // Find method signature and open brace following @Test(expected = ...)
            int searchStart = matcher.end();
            int openBraceIdx = code.indexOf('{', searchStart);

            if (openBraceIdx != -1) {
                int closeBraceIdx = findMatchingBrace(code, openBraceIdx);
                if (closeBraceIdx != -1) {
                    sb.append("@Test");
                    // Append everything between @Test(...) end and opening brace '{'
                    sb.append(code, searchStart, openBraceIdx + 1);

                    String body = code.substring(openBraceIdx + 1, closeBraceIdx);
                    if (!body.contains("assertThrows") && !body.contains("Assertions.assertThrows")) {
                        sb.append("\n        Assertions.assertThrows(").append(exceptionClass).append(", () -> {");
                        sb.append(body);
                        sb.append("\n        });\n    ");
                    } else {
                        sb.append(body);
                    }

                    sb.append("}");
                    lastIndex = closeBraceIdx + 1;
                    rules.add("RULE-JUNIT4-EXPECTED-EXCEPTION-TO-ASSERT-THROWS");
                    continue;
                }
            }

            // Fallback: replace annotation only
            sb.append("@Test");
            lastIndex = matcher.end();
        }
        sb.append(code.substring(lastIndex));

        String res = sb.toString();
        res = addImportIfMissing(res, "org.junit.jupiter.api.Assertions");
        return res;
    }

    private static String modernizeTimeoutAnnotation(String code, List<String> rules) {
        Pattern timeoutPattern = Pattern.compile("@Test\\s*\\(\\s*timeout\\s*=\\s*([0-9]+)L?\\s*\\)");
        Matcher matcher = timeoutPattern.matcher(code);
        if (!matcher.find()) {
            return code;
        }

        StringBuffer sb = new StringBuffer();
        do {
            long millis = Long.parseLong(matcher.group(1));
            String replacement;
            if (millis % 1000 == 0 && millis >= 1000) {
                long seconds = millis / 1000;
                replacement = "@Test\n    @Timeout(" + seconds + ")";
            } else {
                replacement = "@Test\n    @Timeout(value = " + millis + ", unit = TimeUnit.MILLISECONDS)";
            }
            matcher.appendReplacement(sb, Matcher.quoteReplacement(replacement));
            rules.add("RULE-JUNIT4-TIMEOUT-TO-JUPITER-TIMEOUT");
        } while (matcher.find());
        matcher.appendTail(sb);

        String res = sb.toString();
        res = addImportIfMissing(res, "org.junit.jupiter.api.Timeout");
        if (res.contains("TimeUnit.MILLISECONDS")) {
            res = addImportIfMissing(res, "java.util.concurrent.TimeUnit");
        }
        return res;
    }

    private static String modernizeAssertions(String code, List<String> rules) {
        String result = code;

        // 1. Assert.xxx -> Assertions.xxx
        result = result.replaceAll("\\bAssert\\.", "Assertions.");
        result = result.replaceAll("\\bAssert::", "Assertions::");

        // 2. Lexical analysis & parameter reordering
        result = reorderAssertionParameters(result, rules);

        return result;
    }

    /**
     * Lexical token depth-aware parameter inversion for JUnit 4 to JUnit 5 assertions.
     */
    public static String reorderAssertionParameters(String code, List<String> rules) {
        // Match Assertions.<method>( or static imported <method>(
        Set<String> twoArgMethods = Set.of("assertTrue", "assertFalse", "assertNull", "assertNotNull");
        Set<String> threeArgMethods = Set.of("assertEquals", "assertNotEquals", "assertSame", "assertNotSame", "assertArrayEquals");

        Pattern invocationPattern = Pattern.compile("(?:Assertions\\.)?(assertTrue|assertFalse|assertNull|assertNotNull|assertEquals|assertNotEquals|assertSame|assertNotSame|assertArrayEquals)\\s*\\(");
        Matcher matcher = invocationPattern.matcher(code);

        StringBuilder sb = new StringBuilder();
        int lastIndex = 0;

        while (matcher.find()) {
            String methodName = matcher.group(1);
            int methodCallStart = matcher.start();
            int openParen = matcher.end() - 1;

            int closeParen = findMatchingParen(code, openParen);
            if (closeParen == -1) {
                continue;
            }

            String argContent = code.substring(openParen + 1, closeParen);
            List<String> args = splitTopLevelArgs(argContent);

            boolean modifiedArgs = false;
            List<String> newArgs = new ArrayList<>(args);

            if (twoArgMethods.contains(methodName) && args.size() == 2) {
                String first = args.get(0).trim();
                String second = args.get(1).trim();
                // If first argument is string literal or string expression, and second is condition -> swap
                if (isStringExpression(first) && !isStringExpression(second)) {
                    newArgs.set(0, second);
                    newArgs.set(1, first);
                    modifiedArgs = true;
                    rules.add("RULE-JUNIT4-SWAP-ASSERT-MESSAGE-ORDER");
                }
            } else if (threeArgMethods.contains(methodName) && args.size() == 3) {
                String first = args.get(0).trim();
                String second = args.get(1).trim();
                String third = args.get(2).trim();

                // Check if this is a floating point comparison: (expected, actual, delta) -> do not swap
                boolean isDoubleDelta = isNumericOrDelta(third) && isNumericOrDelta(first) && isNumericOrDelta(second);
                if (!isDoubleDelta) {
                    // In JUnit 4: (message, expected, actual)
                    // In JUnit 5: (expected, actual, message)
                    // If first is string expression and third is NOT, it is JUnit 4 format
                    if (isStringExpression(first) && !isStringExpression(third)) {
                        newArgs.set(0, second);
                        newArgs.set(1, third);
                        newArgs.set(2, first);
                        modifiedArgs = true;
                        rules.add("RULE-JUNIT4-SWAP-ASSERT-MESSAGE-ORDER");
                    }
                }
            } else if ("assertEquals".equals(methodName) && args.size() == 4) {
                String first = args.get(0).trim();
                String second = args.get(1).trim();
                String third = args.get(2).trim();
                String fourth = args.get(3).trim();

                // JUnit 4: (message, expected, actual, delta)
                // JUnit 5: (expected, actual, delta, message)
                if (isStringExpression(first) && isNumericOrDelta(fourth)) {
                    newArgs.set(0, second);
                    newArgs.set(1, third);
                    newArgs.set(2, fourth);
                    newArgs.set(3, first);
                    modifiedArgs = true;
                    rules.add("RULE-JUNIT4-SWAP-ASSERT-MESSAGE-ORDER");
                }
            }

            if (modifiedArgs) {
                sb.append(code, lastIndex, openParen + 1);
                sb.append(String.join(", ", newArgs));
                sb.append(")");
                lastIndex = closeParen + 1;
            }
        }

        sb.append(code.substring(lastIndex));
        return sb.toString();
    }

    private static boolean isStringExpression(String arg) {
        String trimmed = arg.trim();
        if (trimmed.startsWith("\"")) {
            return true;
        }
        if (trimmed.contains(" + ") && (trimmed.contains("\"") || trimmed.startsWith("msg") || trimmed.startsWith("message") || trimmed.endsWith("Message"))) {
            return true;
        }
        return trimmed.equalsIgnoreCase("message")
                || trimmed.equalsIgnoreCase("msg")
                || trimmed.equalsIgnoreCase("errorMessage")
                || trimmed.equalsIgnoreCase("failureMessage");
    }

    private static boolean isNumericOrDelta(String arg) {
        String trimmed = arg.trim();
        return trimmed.matches("^[0-9]+(?:\\.[0-9]+)?(?:[fFdDlL])?$")
                || trimmed.equalsIgnoreCase("delta")
                || trimmed.equalsIgnoreCase("epsilon")
                || trimmed.startsWith("0.");
    }

    public static List<String> splitTopLevelArgs(String argString) {
        List<String> args = new ArrayList<>();
        int depthParen = 0;
        int depthBrace = 0;
        int depthBracket = 0;
        boolean inString = false;
        boolean inChar = false;
        boolean inLineComment = false;
        boolean inBlockComment = false;
        StringBuilder current = new StringBuilder();

        for (int i = 0; i < argString.length(); i++) {
            char c = argString.charAt(i);
            char next = (i + 1 < argString.length()) ? argString.charAt(i + 1) : '\0';

            if (inLineComment) {
                current.append(c);
                if (c == '\n') {
                    inLineComment = false;
                }
                continue;
            }
            if (inBlockComment) {
                current.append(c);
                if (c == '*' && next == '/') {
                    current.append(next);
                    i++;
                    inBlockComment = false;
                }
                continue;
            }
            if (inString) {
                current.append(c);
                if (c == '\\' && i + 1 < argString.length()) {
                    current.append(next);
                    i++;
                } else if (c == '"') {
                    inString = false;
                }
                continue;
            }
            if (inChar) {
                current.append(c);
                if (c == '\\' && i + 1 < argString.length()) {
                    current.append(next);
                    i++;
                } else if (c == '\'') {
                    inChar = false;
                }
                continue;
            }

            if (c == '/' && next == '/') {
                inLineComment = true;
                current.append(c).append(next);
                i++;
                continue;
            }
            if (c == '/' && next == '*') {
                inBlockComment = true;
                current.append(c).append(next);
                i++;
                continue;
            }
            if (c == '"') {
                inString = true;
                current.append(c);
                continue;
            }
            if (c == '\'') {
                inChar = true;
                current.append(c);
                continue;
            }
            if (c == '(') {
                depthParen++;
            } else if (c == ')') {
                depthParen--;
            } else if (c == '{') {
                depthBrace++;
            } else if (c == '}') {
                depthBrace--;
            } else if (c == '[') {
                depthBracket++;
            } else if (c == ']') {
                depthBracket--;
            } else if (c == ',' && depthParen == 0 && depthBrace == 0 && depthBracket == 0) {
                args.add(current.toString().trim());
                current.setLength(0);
                continue;
            }
            current.append(c);
        }
        if (!current.isEmpty() && !current.toString().trim().isEmpty()) {
            args.add(current.toString().trim());
        }
        return args;
    }

    private static int findMatchingParen(String text, int openParenIdx) {
        int depth = 0;
        boolean inString = false;
        boolean inChar = false;

        for (int i = openParenIdx; i < text.length(); i++) {
            char c = text.charAt(i);
            char next = (i + 1 < text.length()) ? text.charAt(i + 1) : '\0';

            if (inString) {
                if (c == '\\' && i + 1 < text.length()) {
                    i++;
                } else if (c == '"') {
                    inString = false;
                }
                continue;
            }
            if (inChar) {
                if (c == '\\' && i + 1 < text.length()) {
                    i++;
                } else if (c == '\'') {
                    inChar = false;
                }
                continue;
            }

            if (c == '"') {
                inString = true;
                continue;
            }
            if (c == '\'') {
                inChar = true;
                continue;
            }

            if (c == '(') {
                depth++;
            } else if (c == ')') {
                depth--;
                if (depth == 0) {
                    return i;
                }
            }
        }
        return -1;
    }

    private static int findMatchingBrace(String text, int openBraceIdx) {
        int depth = 0;
        boolean inString = false;
        boolean inChar = false;

        for (int i = openBraceIdx; i < text.length(); i++) {
            char c = text.charAt(i);

            if (inString) {
                if (c == '\\' && i + 1 < text.length()) {
                    i++;
                } else if (c == '"') {
                    inString = false;
                }
                continue;
            }
            if (inChar) {
                if (c == '\\' && i + 1 < text.length()) {
                    i++;
                } else if (c == '\'') {
                    inChar = false;
                }
                continue;
            }

            if (c == '"') {
                inString = true;
                continue;
            }
            if (c == '\'') {
                inChar = true;
                continue;
            }

            if (c == '{') {
                depth++;
            } else if (c == '}') {
                depth--;
                if (depth == 0) {
                    return i;
                }
            }
        }
        return -1;
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

    public static String addImportIfMissing(String code, String fqcn) {
        if (code.contains("import " + fqcn + ";")) {
            return code;
        }
        String importStatement = "import " + fqcn + ";\n";
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
