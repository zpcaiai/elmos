package io.elmos.runner;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

/** Real subprocess tests, no provider or customer code. */
public final class ProcessRunnerConcurrencyTest {
    public static void main(String[] args) throws Exception {
        Path supervisor = args.length == 0 ? null : Path.of(args[0]);
        var runner = new ProcessRunner.Os(supervisor);
        try (var pool = Executors.newFixedThreadPool(4)) {
            var tasks = java.util.stream.IntStream.range(0, 8).mapToObj(i -> pool.submit(() -> {
                var result = runner.run(List.of("/bin/sh", "-c",
                        "dd if=/dev/zero bs=65536 count=64 2>/dev/null"), null, Map.of(), 15);
                if (!result.ok() || result.stdout().length() != (1 << 20)) {
                    throw new AssertionError("bounded capture: " + result);
                }
            })).toList();
            for (var task : tasks) task.get(30, TimeUnit.SECONDS);
        }
        var lines = new AtomicInteger();
        var handle = runner.start(List.of("/bin/sh", "-c",
                "dd if=/dev/zero bs=65536 count=64 2>/dev/null; printf '\\nvalid\\n'"),
                null, Map.of(), line -> {
                    if (line.length() > 16384) throw new AssertionError("unbounded line");
                    lines.incrementAndGet();
                });
        if (handle.waitFor(15, TimeUnit.SECONDS) != 0 || lines.get() != 2) {
            throw new AssertionError("bounded line delivery");
        }
        var noSecrets = runner.run(List.of("/bin/sh", "-c", "printf '%s' \"${ELMOS_RUNNER_ENROLMENT_TOKEN-unset}\""),
                null, Map.of(), 10);
        if (!noSecrets.ok() || !noSecrets.stdout().equals("unset")) throw new AssertionError("environment leak");
        var timeout = runner.run(List.of("/bin/sh", "-c", "sleep 60 & wait"), null, Map.of(), 1);
        if (!timeout.timedOut()) throw new AssertionError("timeout not classified");
        System.out.println("PROCESS RUNNER CONCURRENCY PASSED (8 workers, bounded lines, scrubbed env, timeout)");
    }
}
