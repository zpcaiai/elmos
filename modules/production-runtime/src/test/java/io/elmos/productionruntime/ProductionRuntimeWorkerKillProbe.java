package io.elmos.productionruntime;

import java.nio.file.Files;
import java.nio.file.Path;

/** Disposable child process used only by the local worker-kill recovery test. */
final class ProductionRuntimeWorkerKillProbe {
    private ProductionRuntimeWorkerKillProbe() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 1) throw new IllegalArgumentException("ready file is required");
        Files.writeString(Path.of(args[0]), "READY");
        while (true) Thread.sleep(1_000);
    }
}
