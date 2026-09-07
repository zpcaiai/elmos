package io.elmos.lowering;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

/**
 * Real {@link PolyglotRouteEngineProcessRunner} backed by {@link ProcessBuilder}.
 *
 * Merges stderr into stdout ({@code redirectErrorStream(true)}), matching the
 * pattern already used for external process invocation elsewhere in this
 * codebase (see {@code LocalSpringUpgradeIndependentValidator}): a single
 * reader thread drains combined output, avoiding the classic deadlock where a
 * full stderr pipe blocks a process that is waiting on stdout to be read.
 */
public final class RealPolyglotRouteEngineProcessRunner implements PolyglotRouteEngineProcessRunner {
    @Override
    public ProcessResult run(List<String> command, Path workingDirectory, Map<String, String> environment, Duration timeout) {
        ProcessBuilder builder = new ProcessBuilder(command).directory(workingDirectory.toFile()).redirectErrorStream(true);
        builder.environment().putAll(environment);
        StringBuilder output = new StringBuilder();
        try {
            Process process = builder.start();
            Thread reader = Thread.ofVirtual().start(() -> {
                try (var in = process.inputReader(StandardCharsets.UTF_8)) {
                    char[] buffer = new char[8192];
                    int count;
                    while ((count = in.read(buffer)) >= 0) output.append(buffer, 0, count);
                } catch (IOException ignored) {
                    // Best-effort output collection; exit code and empty output still surface a failure.
                }
            });
            boolean completed = process.waitFor(timeout.toMillis(), TimeUnit.MILLISECONDS);
            if (!completed) {
                process.destroyForcibly();
                reader.join(5_000);
                return new ProcessResult(-1, output.toString(), "PROCESS_TIMEOUT");
            }
            reader.join(5_000);
            return new ProcessResult(process.exitValue(), output.toString(), "");
        } catch (IOException error) {
            return new ProcessResult(-1, "", "PROCESS_START_FAILED:" + error.getMessage());
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            return new ProcessResult(-1, "", "PROCESS_INTERRUPTED");
        }
    }
}
