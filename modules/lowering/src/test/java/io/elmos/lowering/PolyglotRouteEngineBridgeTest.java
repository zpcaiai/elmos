package io.elmos.lowering;

import io.elmos.uir.UirModels;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.Map;

import static io.elmos.lowering.LoweringModels.*;
import static org.junit.jupiter.api.Assertions.*;

/**
 * Exercises {@link PolyglotRouteEngineBridge}'s own logic -- argument construction,
 * response parsing, splicing, fail-closed conditions -- against a fake
 * {@link PolyglotRouteEngineProcessRunner} that never actually shells out to Python.
 * This proves the bridge's wiring is correct without requiring
 * {@code engines/polyglot-route-engine}'s exact Python toolchain to be installed on
 * the machine running these tests.
 */
class PolyglotRouteEngineBridgeTest {

    // Exact real output of engines/polyglot-route-engine's emitter.emit() for a two-branch
    // add(a, b) function, captured by running the emitter directly (see engine.py/emitter.py).
    private static final String JAVA_EMITTED =
            "public final class Migrated {\n"
            + "    public static long add(long a, long b) {\n"
            + "        if ((a < b)) {\n"
            + "            return a;\n"
            + "        }\n"
            + "        return (a + b);\n"
            + "    }\n"
            + "}\n";
    private static final String TYPESCRIPT_EMITTED =
            "export function add(a: number, b: number): number {\n"
            + "    if ((a < b)) {\n"
            + "        return a;\n"
            + "    }\n"
            + "    return (a + b);\n"
            + "}\n";

    @Test void extractBodyStripsTheJavaWrapperAndKeepsNestedIndentation() {
        String body = PolyglotRouteEngineBridge.extractBody("java", JAVA_EMITTED);
        assertEquals("if ((a < b)) {\n    return a;\n}\nreturn (a + b);\n", body);
    }

    @Test void extractBodyStripsTheCsharpAllmanWrapper() {
        String csharp = "public static class Migrated\n{\n    public static long add(long a, long b) {\n"
                + "        if ((a < b)) {\n            return a;\n        }\n        return (a + b);\n    }\n}\n";
        String body = PolyglotRouteEngineBridge.extractBody("csharp", csharp);
        assertEquals("if ((a < b)) {\n    return a;\n}\nreturn (a + b);\n", body);
    }

    @Test void extractBodyStripsThePythonModuleHeaderAndDefLine() {
        String python = "from __future__ import annotations\n\ndef add(a: int, b: int) -> int:\n"
                + "    if (a < b):\n        return a\n    return (a + b)\n";
        String body = PolyglotRouteEngineBridge.extractBody("python", python);
        assertEquals("if (a < b):\n    return a\nreturn (a + b)\n", body);
    }

    @Test void extractBodyStripsTheTypescriptFunctionWrapper() {
        String body = PolyglotRouteEngineBridge.extractBody("typescript", TYPESCRIPT_EMITTED);
        assertEquals("if ((a < b)) {\n    return a;\n}\nreturn (a + b);\n", body);
    }

    @Test void constructorRejectsAnUnsupportedLanguage() {
        assertThrows(IllegalArgumentException.class, () -> new PolyglotRouteEngineBridge(
                "cobol", "java", Path.of("."), "python3", (c, w, e, t) -> null, Duration.ofSeconds(5)));
    }

    @Test void constructorRejectsTheSameSourceAndTargetLanguage() {
        assertThrows(IllegalArgumentException.class, () -> new PolyglotRouteEngineBridge(
                "java", "java", Path.of("."), "python3", (c, w, e, t) -> null, Duration.ofSeconds(5)));
    }

    @Test void emitThrowsWhenSourceTextIsMissingFromTheDeclaration() {
        PolyglotRouteEngineBridge bridge = bridge((c, w, e, t) -> {
            throw new AssertionError("must not shell out when source text is unavailable");
        });
        EmissionRequest request = new EmissionRequest(plan("typescript"), declaration(Map.of()), List.of(), "faithful");

        var error = assertThrows(IllegalStateException.class, () -> bridge.emit(request));
        assertTrue(error.getMessage().startsWith("TARGET_EMITTER_SOURCE_TEXT_UNAVAILABLE"));
    }

    @Test void emitInvokesTheEngineAndReturnsJustTheExtractedBody() {
        PolyglotRouteEngineBridge bridge = bridge(new FakeEmitRunner("typescript", TYPESCRIPT_EMITTED, "add"));
        EmissionRequest request = new EmissionRequest(
                plan("typescript"), declaration(Map.of("sourceText", "def add(a, b):\n    return a + b\n")),
                List.of(), "faithful");

        Emission emission = bridge.emit(request);

        assertEquals("faithful", emission.phase());
        assertEquals("if ((a < b)) {\n    return a;\n}\nreturn (a + b);\n", emission.body());
        assertEquals(plan("typescript").operationIds(), emission.sourceOperationIds());
    }

    @Test void emitThrowsWithTheEngineReasonWhenTheProcessFails() {
        PolyglotRouteEngineBridge bridge = bridge((c, w, e, t) ->
                new PolyglotRouteEngineProcessRunner.ProcessResult(
                        2, "{\"status\": \"BLOCKED\", \"reason\": \"UNSUPPORTED_STATEMENT:for\"}", ""));
        EmissionRequest request = new EmissionRequest(
                plan("typescript"), declaration(Map.of("sourceText", "def loop():\n    for x in y: pass\n")),
                List.of(), "faithful");

        var error = assertThrows(IllegalStateException.class, () -> bridge.emit(request));
        assertTrue(error.getMessage().contains("UNSUPPORTED_STATEMENT:for"), error.getMessage());
    }

    @Test void validateReturnsFailedWhenThePlanTargetsADifferentLanguage() {
        PolyglotRouteEngineBridge bridge = bridge((c, w, e, t) -> {
            throw new AssertionError("must not shell out on a language mismatch");
        });
        Emission emission = new Emission("faithful", "return a + b;\n", List.of(), List.of(), List.of("op-1"), List.of());
        ValidationRequest request = new ValidationRequest(plan("java"), emission, Path.of("."));

        StaticValidation result = bridge("csharp").validate(request);

        assertFalse(result.passed());
        assertTrue(result.diagnostics().get(0).startsWith("STATIC_VALIDATOR_LANGUAGE_MISMATCH"));
    }

    @Test void validateReturnsFailedWhenTheEmissionHasNoBody() {
        PolyglotRouteEngineBridge bridge = bridge((c, w, e, t) -> {
            throw new AssertionError("must not shell out with no emission body");
        });
        Emission blank = new Emission("faithful", "  ", List.of(), List.of(), List.of("op-1"), List.of());
        StaticValidation result = bridge.validate(new ValidationRequest(plan("typescript"), blank, Path.of(".")));

        assertFalse(result.passed());
        assertEquals("STATIC_VALIDATOR_EMISSION_BODY_UNAVAILABLE", result.diagnostics().get(0));
    }

    @Test void validateReturnsFailedWhenNoGeneratedBodyMarkerExists(@TempDir Path repository) throws Exception {
        Files.writeString(repository.resolve("Migrated.ts"), "export function add() { return 0; }\n", StandardCharsets.UTF_8);
        PolyglotRouteEngineBridge bridge = bridge((c, w, e, t) -> {
            throw new AssertionError("must not shell out with no marker to splice into");
        });
        Emission emission = new Emission("faithful", "return a + b;\n", List.of(), List.of(), List.of("op-1"), List.of());
        CallablePlan plan = plan("typescript");
        StaticValidation result = bridge.validate(new ValidationRequest(plan, emission, repository));

        assertFalse(result.passed());
        assertTrue(result.diagnostics().get(0).contains("GENERATED_REGION_NOT_UNIQUE"));
    }

    @Test void validateSplicesIntoTheRealTargetFileAndReportsARealCompilePass(@TempDir Path repository) throws Exception {
        CallablePlan plan = plan("typescript");
        String skeleton = "export function add(a: number, b: number): number {\n"
                + "    // <generated-body id=\"" + plan.targetDeclarationId() + "\">\n"
                + "    return 0;\n"
                + "    // </generated-body>\n"
                + "}\n";
        Files.writeString(repository.resolve(plan.targetFile()), skeleton, StandardCharsets.UTF_8);
        FakeCheckRunner runner = new FakeCheckRunner(true);
        PolyglotRouteEngineBridge bridge = bridge(runner);
        Emission emission = new Emission("faithful", "return a + b;", List.of(), List.of(), List.of("op-1"), List.of());

        StaticValidation result = bridge.validate(new ValidationRequest(plan, emission, repository));

        assertTrue(result.passed());
        assertEquals(Status.PASSED, result.syntax());
        assertEquals(Status.PASSED, result.types());
        assertTrue(runner.checkedFileContent.contains("return a + b;"));
        assertTrue(runner.checkedFileContent.contains(plan.targetDeclarationId()));
    }

    @Test void validateReturnsFailedWithDiagnosticsWhenTheCompileFails(@TempDir Path repository) throws Exception {
        CallablePlan plan = plan("typescript");
        String skeleton = "export function add(a: number, b: number): number {\n"
                + "    // <generated-body id=\"" + plan.targetDeclarationId() + "\">\n"
                + "    return 0;\n"
                + "    // </generated-body>\n"
                + "}\n";
        Files.writeString(repository.resolve(plan.targetFile()), skeleton, StandardCharsets.UTF_8);
        PolyglotRouteEngineBridge bridge = bridge(new FakeCheckRunner(false));
        Emission emission = new Emission("faithful", "return a +;", List.of(), List.of(), List.of("op-1"), List.of());

        StaticValidation result = bridge.validate(new ValidationRequest(plan, emission, repository));

        assertFalse(result.passed());
        assertEquals(Status.FAILED, result.semanticChecks());
        assertFalse(result.diagnostics().isEmpty());
    }

    private static PolyglotRouteEngineBridge bridge(PolyglotRouteEngineProcessRunner runner) {
        return new PolyglotRouteEngineBridge("python", "typescript", Path.of("engines/polyglot-route-engine"),
                "python3", runner, Duration.ofSeconds(30));
    }

    private static PolyglotRouteEngineBridge bridge(String targetLanguage) {
        return new PolyglotRouteEngineBridge("java", targetLanguage, Path.of("engines/polyglot-route-engine"),
                "python3", (c, w, e, t) -> null, Duration.ofSeconds(30));
    }

    private static CallablePlan plan(String targetLanguage) {
        return new CallablePlan("callable-plan:add", "module:orders", "decl:source-add", "decl:target-add",
                "Migrated." + extension(targetLanguage), targetLanguage, "planned",
                List.of("op-1", "op-2"), List.of(), List.of(), List.of(),
                List.of(), List.of(), "input-hash", "rules-hash");
    }

    private static String extension(String language) {
        return switch (language) {
            case "java" -> "java";
            case "csharp" -> "cs";
            case "python" -> "py";
            default -> "ts";
        };
    }

    private static UirModels.Declaration declaration(Map<String, Object> languageSemantics) {
        return new UirModels.Declaration("decl:source-add", "method", "add", "source.add", null, "public",
                List.of(), "type:int", List.of(), List.of(), "region:body", List.of("sym:add"), languageSemantics);
    }

    /** Simulates the real `elmos-polyglot-route emit` CLI: writes an emission-report.json and the emitted file. */
    private record FakeEmitRunner(String targetLanguage, String emittedContent, String functionName)
            implements PolyglotRouteEngineProcessRunner {
        @Override public ProcessResult run(List<String> command, Path workingDirectory, Map<String, String> environment, Duration timeout) {
            assertEquals("emit", command.get(3));
            Path output = Path.of(command.get(command.indexOf("--output") + 1));
            try {
                Files.createDirectories(output);
                String fileName = targetLanguage.equals("typescript") ? "migrated.ts" : "migrated";
                Files.writeString(output.resolve(fileName), emittedContent, StandardCharsets.UTF_8);
                String report = "{"
                        + "\"schema_version\":\"1.0.0\","
                        + "\"kind\":\"elmos.single-unit-emission\","
                        + "\"status\":\"EMITTED\","
                        + "\"target\":{\"path\":\"" + fileName + "\",\"language\":\"" + targetLanguage + "\","
                        + "\"function_name\":\"" + functionName + "\"}"
                        + "}";
                Files.writeString(output.resolve("emission-report.json"), report, StandardCharsets.UTF_8);
            } catch (Exception error) {
                throw new AssertionError(error);
            }
            return new ProcessResult(0, "{}", "");
        }
    }

    /** Simulates the real `elmos-polyglot-route check` CLI without ever invoking a compiler. */
    private static final class FakeCheckRunner implements PolyglotRouteEngineProcessRunner {
        private final boolean passes;
        private String checkedFileContent = "";

        private FakeCheckRunner(boolean passes) { this.passes = passes; }

        @Override public ProcessResult run(List<String> command, Path workingDirectory, Map<String, String> environment, Duration timeout) {
            assertEquals("check", command.get(3));
            try {
                Path file = Path.of(command.get(command.indexOf("--file") + 1));
                checkedFileContent = Files.readString(file, StandardCharsets.UTF_8);
                Path output = Path.of(command.get(command.indexOf("--output") + 1));
                Files.createDirectories(output);
                String status = passes ? "PASSED" : "FAILED";
                String diagnostics = passes ? "[]" : "[\"TS1005: ';' expected.\"]";
                String report = "{\"schema_version\":\"1.0.0\",\"kind\":\"elmos.single-unit-static-check\","
                        + "\"status\":\"" + status + "\",\"diagnostics\":" + diagnostics + "}";
                Files.writeString(output.resolve("check-report.json"), report, StandardCharsets.UTF_8);
            } catch (Exception error) {
                throw new AssertionError(error);
            }
            return new ProcessResult(0, "{}", "");
        }
    }
}
