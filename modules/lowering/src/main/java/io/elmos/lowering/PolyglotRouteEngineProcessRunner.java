package io.elmos.lowering;

import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.Map;

/**
 * Runs one subprocess for {@link PolyglotRouteEngineBridge} and returns its result.
 *
 * Kept as a separate seam (rather than calling {@link ProcessBuilder} directly inside
 * the bridge) so the bridge's own logic -- argument construction, response parsing,
 * fail-closed conditions -- can be unit tested with a fake runner, without requiring
 * the real {@code engines/polyglot-route-engine} Python toolchain to be installed.
 */
@FunctionalInterface
public interface PolyglotRouteEngineProcessRunner {
    ProcessResult run(List<String> command, Path workingDirectory, Map<String, String> environment, Duration timeout);

    record ProcessResult(int exitCode, String stdout, String stderr) {}
}
