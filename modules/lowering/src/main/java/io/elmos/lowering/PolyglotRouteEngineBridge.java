package io.elmos.lowering;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.uir.UirModels;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.time.Duration;
import java.util.*;

import static io.elmos.lowering.LoweringModels.*;

/**
 * Real {@link TargetEmitter} and {@link StaticValidator} that delegate to the already
 * locally-certified {@code engines/polyglot-route-engine} (see its README and
 * {@code routes/inventory.json}), instead of reinventing a second translation backend
 * inside Lowering.
 *
 * <p>Scope is deliberately narrow. This bridge only ever produces or validates code
 * inside the engine's own {@code typed-pure-function-v1} profile, for exactly the
 * (sourceLanguage, targetLanguage) pair it is constructed with. Everything outside
 * that -- a declaration whose engine analysis is rejected, a plan for a different
 * language pair, a missing input -- fails closed: {@link #emit} throws (the caller,
 * {@code MethodBodyLoweringService}, already wraps each plan's emit+validate in a
 * try/catch and records a {@code "blocked"} result), and {@link #validate} returns a
 * failed {@link StaticValidation} rather than throwing, matching how the interface is
 * consumed via {@code StaticValidation.passed()}.
 *
 * <h2>What this bridge needs that Lowering's UIR pipeline does not yet supply</h2>
 * {@link #emit} requires the exact original source text of the declaration, which it
 * reads from {@code declaration.languageSemantics().get("sourceText")}. Nothing in
 * {@code modules/uir}'s current PSP-&gt;UIR lifter populates that key, so until it (or
 * an equivalent real source lookup) is wired in, this bridge will fail closed with
 * {@code TARGET_EMITTER_SOURCE_TEXT_UNAVAILABLE} for declarations lifted through the
 * production pipeline. That gap is intentionally not papered over here: inventing a
 * UIR-to-source-text renderer would itself be reinventing translation logic, which is
 * exactly what delegating to the real engine is meant to avoid. Tests exercise this
 * bridge with {@code languageSemantics} populated directly, proving the delegation
 * itself is real; wiring a real {@code sourceText} supplier through the UIR lifter is
 * tracked as separate follow-up work.
 *
 * <h2>How validation stays real without a behavior-case corpus</h2>
 * The polyglot-route-engine's own {@code validate()} requires an independent
 * behavior-case corpus and actually executes the emitted code; Lowering's
 * {@link StaticValidator} is deliberately syntax/symbol/type-only and carries no
 * behavior cases anywhere in its model. Rather than fabricate cases, {@link #validate}
 * uses the engine's {@code check} entry point (compile/type-check only, no execution)
 * against the emitted body spliced into the real target file Skeleton already wrote
 * (read-only; this bridge never writes to the target repository). All four
 * {@link StaticValidation} status fields are set together from that one real compiler
 * outcome, because a plain compiler pass/fail does not distinguish syntax from symbol
 * from type errors with the granularity the record's separate fields might suggest.
 */
public final class PolyglotRouteEngineBridge implements TargetEmitter, StaticValidator {
    private static final Set<String> SUPPORTED_LANGUAGES = Set.of("java", "python", "csharp", "typescript");
    private static final Map<String, String> SOURCE_EXTENSION = Map.of(
            "java", ".java", "python", ".py", "csharp", ".cs", "typescript", ".ts");
    private static final String BACKEND_REF = "elmos-polyglot-route-engine:check";

    private final String sourceLanguage;
    private final String targetLanguage;
    private final Path engineRoot;
    private final String pythonExecutable;
    private final PolyglotRouteEngineProcessRunner runner;
    private final Duration timeout;
    private final ObjectMapper json;

    public PolyglotRouteEngineBridge(
            String sourceLanguage,
            String targetLanguage,
            Path engineRoot,
            String pythonExecutable,
            PolyglotRouteEngineProcessRunner runner,
            Duration timeout
    ) {
        if (!SUPPORTED_LANGUAGES.contains(sourceLanguage) || !SUPPORTED_LANGUAGES.contains(targetLanguage)) {
            throw new IllegalArgumentException("POLYGLOT_ROUTE_BRIDGE_UNSUPPORTED_LANGUAGE");
        }
        if (sourceLanguage.equals(targetLanguage)) {
            throw new IllegalArgumentException("POLYGLOT_ROUTE_BRIDGE_SOURCE_AND_TARGET_MUST_DIFFER");
        }
        this.sourceLanguage = sourceLanguage;
        this.targetLanguage = targetLanguage;
        this.engineRoot = Objects.requireNonNull(engineRoot).toAbsolutePath().normalize();
        this.pythonExecutable = Objects.requireNonNull(pythonExecutable);
        this.runner = Objects.requireNonNull(runner);
        this.timeout = Objects.requireNonNull(timeout);
        this.json = new ObjectMapper().findAndRegisterModules();
    }

    @Override
    public Emission emit(EmissionRequest request) {
        Objects.requireNonNull(request);
        if (!targetLanguage.equals(request.plan().targetLanguage())) {
            throw new IllegalStateException("TARGET_EMITTER_LANGUAGE_MISMATCH:" + request.plan().targetLanguage());
        }
        UirModelsDeclarationAccess declaration = requireDeclaration(request);
        String sourceText = declaration.sourceText();
        String functionName = declaration.functionName();

        Path workDir = null;
        try {
            workDir = createTempDirectory("emit");
            Path sourceFile = workDir.resolve("source" + SOURCE_EXTENSION.get(sourceLanguage));
            Files.writeString(sourceFile, sourceText, StandardCharsets.UTF_8);
            Path outputDir = workDir.resolve("out");
            List<String> command = List.of(
                    pythonExecutable, "-m", "elmos_polyglot_route.cli", "emit",
                    "--source", sourceFile.toString(),
                    "--source-language", sourceLanguage,
                    "--target-language", targetLanguage,
                    "--function", functionName,
                    "--output", outputDir.toString()
            );
            PolyglotRouteEngineProcessRunner.ProcessResult result = runner.run(command, engineRoot, environment(), timeout);
            if (result.exitCode() != 0) {
                throw new IllegalStateException("TARGET_EMITTER_ENGINE_FAILED:" + reason(result));
            }
            Path reportFile = outputDir.resolve("emission-report.json");
            if (!Files.isRegularFile(reportFile, LinkOption.NOFOLLOW_LINKS)) {
                throw new IllegalStateException("TARGET_EMITTER_REPORT_MISSING");
            }
            JsonNode report = json.readTree(reportFile.toFile());
            String targetPath = report.path("target").path("path").asText("");
            if (targetPath.isBlank()) throw new IllegalStateException("TARGET_EMITTER_REPORT_INVALID");
            Path emittedFile = outputDir.resolve(targetPath).normalize();
            if (!emittedFile.startsWith(outputDir)) {
                throw new IllegalStateException("TARGET_EMITTER_OUTPUT_PATH_ESCAPES");
            }
            String emittedContent = Files.readString(emittedFile, StandardCharsets.UTF_8);
            String body = extractBody(targetLanguage, emittedContent);
            return new Emission(request.phase(), body, List.of(), List.of(), request.plan().operationIds(), List.of());
        } catch (IOException error) {
            throw new UncheckedIOException("TARGET_EMITTER_IO_FAILED", error);
        } finally {
            deleteTree(workDir);
        }
    }

    @Override
    public StaticValidation validate(ValidationRequest request) {
        Objects.requireNonNull(request);
        CallablePlan plan = request.plan();
        Emission emission = request.emission();
        if (!targetLanguage.equals(plan.targetLanguage())) {
            return failed(plan, "STATIC_VALIDATOR_LANGUAGE_MISMATCH:" + plan.targetLanguage());
        }
        if (emission == null || emission.body() == null || emission.body().isBlank()) {
            return failed(plan, "STATIC_VALIDATOR_EMISSION_BODY_UNAVAILABLE");
        }

        String spliced;
        try {
            Path root = request.targetRepository().toRealPath(LinkOption.NOFOLLOW_LINKS);
            Path target = root.resolve(plan.targetFile()).normalize();
            if (!target.startsWith(root) || Files.isSymbolicLink(target)
                    || !Files.isRegularFile(target, LinkOption.NOFOLLOW_LINKS)) {
                return failed(plan, "STATIC_VALIDATOR_TARGET_FILE_UNSAFE:" + plan.targetFile());
            }
            String current = Files.readString(target, StandardCharsets.UTF_8);
            spliced = splice(current, plan.targetDeclarationId(), emission.body());
        } catch (IOException | IllegalStateException error) {
            return failed(plan, "STATIC_VALIDATOR_TARGET_FILE_UNREADABLE:" + safeMessage(error));
        }

        Path workDir;
        try {
            workDir = createTempDirectory("check");
        } catch (IOException error) {
            return failed(plan, "STATIC_VALIDATOR_WORKSPACE_UNAVAILABLE");
        }
        try {
            Path splicedFile = workDir.resolve("spliced" + SOURCE_EXTENSION.get(targetLanguage));
            Files.writeString(splicedFile, spliced, StandardCharsets.UTF_8);
            Path outputDir = workDir.resolve("out");
            List<String> command = List.of(
                    pythonExecutable, "-m", "elmos_polyglot_route.cli", "check",
                    "--target-language", targetLanguage,
                    "--file", splicedFile.toString(),
                    "--output", outputDir.toString()
            );
            PolyglotRouteEngineProcessRunner.ProcessResult result = runner.run(command, engineRoot, environment(), timeout);
            if (result.exitCode() != 0) {
                return failed(plan, "STATIC_VALIDATOR_ENGINE_FAILED:" + reason(result));
            }
            Path reportFile = outputDir.resolve("check-report.json");
            if (!Files.isRegularFile(reportFile, LinkOption.NOFOLLOW_LINKS)) {
                return failed(plan, "STATIC_VALIDATOR_REPORT_MISSING");
            }
            JsonNode report = json.readTree(reportFile.toFile());
            boolean passed = "PASSED".equals(report.path("status").asText(""));
            List<String> diagnostics = new ArrayList<>();
            report.path("diagnostics").forEach(node -> diagnostics.add(node.asText()));
            Status status = passed ? Status.PASSED : Status.FAILED;
            return new StaticValidation(
                    plan.targetDeclarationId(), status, status, status, status,
                    List.copyOf(diagnostics), plan.openObligations(), BACKEND_REF
            );
        } catch (IOException error) {
            return failed(plan, "STATIC_VALIDATOR_IO_FAILED:" + safeMessage(error));
        } finally {
            deleteTree(workDir);
        }
    }

    private UirModelsDeclarationAccess requireDeclaration(EmissionRequest request) {
        UirModels.Declaration declaration = request.declaration();
        if (declaration == null) throw new IllegalStateException("TARGET_EMITTER_DECLARATION_UNAVAILABLE");
        Object rawSourceText = declaration.languageSemantics().get("sourceText");
        if (!(rawSourceText instanceof String sourceText) || sourceText.isBlank()) {
            throw new IllegalStateException("TARGET_EMITTER_SOURCE_TEXT_UNAVAILABLE:" + declaration.declarationId());
        }
        String functionName = declaration.name();
        if (functionName == null || functionName.isBlank()) {
            throw new IllegalStateException("TARGET_EMITTER_FUNCTION_NAME_UNAVAILABLE:" + declaration.declarationId());
        }
        return new UirModelsDeclarationAccess(sourceText, functionName);
    }

    private record UirModelsDeclarationAccess(String sourceText, String functionName) {}

    private Map<String, String> environment() {
        return Map.of("PYTHONPATH", engineRoot.resolve("src").toString(), "NO_COLOR", "1");
    }

    private String reason(PolyglotRouteEngineProcessRunner.ProcessResult result) {
        try {
            JsonNode node = json.readTree(result.stdout());
            if (node.has("reason")) return node.get("reason").asText();
        } catch (IOException ignored) {
            // Fall through to raw output below; the subprocess did not produce the expected JSON envelope.
        }
        String combined = (result.stdout() + " " + result.stderr()).strip();
        return combined.isBlank() ? "UNKNOWN" : combined.substring(0, Math.min(500, combined.length()));
    }

    private static String safeMessage(Exception error) {
        return error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage();
    }

    private static StaticValidation failed(CallablePlan plan, String reason) {
        return new StaticValidation(
                plan.targetDeclarationId(), Status.FAILED, Status.FAILED, Status.FAILED, Status.FAILED,
                List.of(reason), plan.openObligations(), BACKEND_REF
        );
    }

    /** Replicates {@link GeneratedRegionPatchManager}'s marker search, read-only: never writes to disk. */
    private static String splice(String current, String targetDeclarationId, String body) {
        String begin = "<generated-body id=\"" + targetDeclarationId + "\">";
        String end = "</generated-body>";
        int beginAt = current.indexOf(begin);
        int endAt = current.indexOf(end, beginAt + begin.length());
        if (beginAt < 0 || endAt < 0 || current.indexOf(begin, beginAt + 1) >= 0) {
            throw new IllegalStateException("GENERATED_REGION_NOT_UNIQUE:" + targetDeclarationId);
        }
        int contentStart = current.indexOf('\n', beginAt + begin.length()) + 1;
        int endLineStart = current.lastIndexOf('\n', endAt) + 1;
        if (contentStart <= 0 || endLineStart < contentStart) {
            throw new IllegalStateException("GENERATED_REGION_LINES_INVALID");
        }
        return current.substring(0, contentStart) + body.strip() + "\n" + current.substring(endLineStart);
    }

    /**
     * Strips emitter.py's deterministic class/function wrapper down to just the inner
     * statement block, dedenting so nested if/else blocks keep their relative
     * indentation. This is coupled, on purpose and by necessity, to
     * {@code engines/polyglot-route-engine}'s exact emission shape for each language;
     * a change to that emitter's formatting requires a matching change here.
     */
    static String extractBody(String language, String content) {
        String normalized = content.replace("\r\n", "\n");
        if (normalized.endsWith("\n")) normalized = normalized.substring(0, normalized.length() - 1);
        List<String> lines = new ArrayList<>(Arrays.asList(normalized.split("\n", -1)));
        int headerLines;
        int trailerLines;
        int dedent;
        switch (language) {
            case "java" -> { headerLines = 2; trailerLines = 2; dedent = 8; }
            case "csharp" -> { headerLines = 3; trailerLines = 2; dedent = 8; }
            case "python" -> { headerLines = 3; trailerLines = 0; dedent = 4; }
            case "typescript" -> { headerLines = 1; trailerLines = 1; dedent = 4; }
            default -> throw new IllegalStateException("TARGET_EMITTER_UNSUPPORTED_LANGUAGE:" + language);
        }
        if (lines.size() < headerLines + trailerLines + 1) {
            throw new IllegalStateException("TARGET_EMITTER_EMITTED_SHAPE_UNEXPECTED:" + language);
        }
        List<String> body = lines.subList(headerLines, lines.size() - trailerLines);
        String prefix = " ".repeat(dedent);
        StringBuilder result = new StringBuilder();
        for (String line : body) {
            result.append(line.startsWith(prefix) ? line.substring(dedent) : line).append('\n');
        }
        return result.toString();
    }

    private static Path createTempDirectory(String prefix) throws IOException {
        return Files.createTempDirectory("elmos-lowering-bridge-" + prefix + "-");
    }

    private static void deleteTree(Path root) {
        if (root == null || !Files.exists(root, LinkOption.NOFOLLOW_LINKS)) return;
        try {
            Files.walkFileTree(root, new SimpleFileVisitor<>() {
                @Override public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) throws IOException {
                    Files.deleteIfExists(file);
                    return FileVisitResult.CONTINUE;
                }

                @Override public FileVisitResult postVisitDirectory(Path dir, IOException error) throws IOException {
                    Files.deleteIfExists(dir);
                    return FileVisitResult.CONTINUE;
                }
            });
        } catch (IOException ignored) {
            // Best-effort temp workspace cleanup; leaving stray temp files behind is not fail-closed-relevant.
        }
    }
}
