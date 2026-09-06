package io.elmos.integrations;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.Path;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import static org.junit.jupiter.api.Assertions.*;

class WorkspaceLocksTest {
    @TempDir Path root;

    @Test void supportsReentryNonblockingCleanupAndSafeWaiterRetirement() throws Exception {
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            for (int repeat = 0; repeat < 50; repeat++) {
                java.util.concurrent.Future<Boolean> waiter;
                try (var outer = WorkspaceLocks.acquire(root); var nested = WorkspaceLocks.acquire(root)) {
                    assertNull(executor.submit(() -> WorkspaceLocks.tryAcquire(root)).get(2, TimeUnit.SECONDS));
                    waiter = executor.submit(() -> {
                        try (var ignored = WorkspaceLocks.acquire(root)) { return true; }
                    });
                    assertNotNull(nested);
                }
                assertTrue(waiter.get(2, TimeUnit.SECONDS));
                try (var fresh = WorkspaceLocks.tryAcquire(root)) { assertNotNull(fresh); }
            }
        }
    }
}
